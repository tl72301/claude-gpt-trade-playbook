"""Stage 1 go/no-go. Criteria are fixed here, before any money is spent.

The scout cannot answer the research question (2 lineages per model). It asks
whether the pilot COULD answer it, and what the pilot will really cost.

  C1 health       refusals < 5% of calls, no served-model mismatches, and fewer than
                  half of generations lost to improver crashes or policy violations
  C2 headroom     the seed solver scores 20-70% on the sealed set under both models
  C3 loop works   each model's lineages gain >= 1 dev task on average, and at least
                  one procedure (improver.py) edit is accepted per model
  C4 divergence   at least one lineage per model ends with a procedure different
                  from the seed (otherwise there is nothing to specialize)
  C5 noise        the pilot's minimum detectable specialization (80% power, 5% two-
                  sided), estimated from gen-0 replicate variance, is <= 15% of the
                  pilot's sealed set
  C6 cost         projected pilot cost at 1.5x observed output tokens fits in the
                  remaining budget
"""

from __future__ import annotations

import json
import math
from pathlib import Path


def _sd(xs):
    xs = list(xs)
    if len(xs) < 2:
        return float("nan")
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def decide(scout_dir: Path, scout_cfg: dict, pilot_cfg: dict, pilot_sim_dir: Path, prices: dict,
           total_budget: float, seed_improver: str, model_budgets: dict | None = None) -> dict:
    """model_budgets: {model key: dollars loaded with that vendor}; falls back to total_budget."""
    from .budget import calibrated, observed_profile

    spend = [json.loads(l) for l in (scout_dir / "spend.jsonl").read_text().splitlines() if l.strip()]
    spent = sum(r.get("usd", 0.0) for r in spend)
    checks = []

    def add(name, passed, detail, fix):
        checks.append({"criterion": name, "pass": bool(passed), "detail": detail, "if_failed": fix})

    # C1 health
    n = max(1, len(spend))
    refusal_rate = sum(r["refused"] for r in spend) / n
    mismatches = sum(r["mismatch"] for r in spend)
    bad, gens = 0, 0
    for h in (scout_dir / "evolution").glob("*/history.json"):
        for r in json.loads(h.read_text())[1:]:
            gens += 1
            bad += (r.get("status", "").startswith("improver_")
                    or r.get("status") in ("policy_violation", "no_proc_change"))
    add("C1 health", refusal_rate < 0.05 and mismatches == 0 and bad < 0.5 * max(1, gens),
        f"refusals {refusal_rate:.1%}, mismatches {mismatches}, broken generations {bad}/{gens}",
        "Read the improver replies in evolution/*/history.json; fix the seed prompt/format or swap the model.")

    # C2 headroom
    base = json.loads((scout_dir / "sealed_baselines.json").read_text())
    rates = {k: v["mean"] / v["n"] for k, v in base.items()}
    add("C2 headroom", all(0.2 <= r <= 0.7 for r in rates.values()),
        ", ".join(f"{k}: {r:.0%}" for k, r in rates.items()),
        "Change tasks.partitions depths (harder if a model is above 70%, easier if below 20%).")

    # C3 / C4 loop works, procedures diverge
    per_model = {}
    for d in sorted((scout_dir / "evolution").glob("*")):
        hist = json.loads((d / "history.json").read_text())
        key = d.name[0]
        final_proc = (d / "gens" / f"g{len(hist) - 1:03d}" / "improver.py").read_text()
        m = per_model.setdefault(key, {"gain": [], "proc_accepted": 0, "diverged": 0})
        m["gain"].append(hist[-1]["bar"] - hist[0]["bar"])
        m["proc_accepted"] += sum(bool(r.get("proc_edit_accepted")) for r in hist)
        m["diverged"] += final_proc != seed_improver
    add("C3 loop works",
        all(sum(m["gain"]) / len(m["gain"]) >= 1 and m["proc_accepted"] >= 1 for m in per_model.values()),
        "; ".join(f"{k}: mean dev gain {sum(m['gain']) / len(m['gain']):+.1f}, procedure edits kept {m['proc_accepted']}"
                  for k, m in per_model.items()),
        "If gains are ~0: raise improver_budget or generations. If procedure edits are never kept: "
        "the brain-swap question is moot -- report that as the finding.")
    add("C4 divergence", all(m["diverged"] >= 1 for m in per_model.values()),
        "; ".join(f"{k}: {m['diverged']} lineage(s) changed their procedure" for k, m in per_model.items()),
        "Same as C3: without procedure change there is nothing to specialize.")

    # C5 noise -> minimum detectable effect for the pilot
    cells = [json.loads(p.read_text()) for p in (scout_dir / "audits").glob("*/result.json")]
    g0 = [c for c in cells if c["checkpoint"] == 0]
    sds = [_sd(c["gain"] for c in g0 if c["op"] == op) for op in scout_cfg["models"]]
    sd_gain = math.sqrt(sum(s * s for s in sds) / len(sds)) if all(s == s for s in sds) else float("nan")
    scale = pilot_cfg["tasks"]["partitions"]["sealed"]["n"] / scout_cfg["tasks"]["partitions"]["sealed"]["n"]
    reps = pilot_cfg["audits"].get("replicates_per_cell", 1)
    sd_pilot = sd_gain * math.sqrt(scale) / math.sqrt(reps)   # count SD grows ~ sqrt(n); replicates average
    sd_d = math.sqrt(2) * sd_pilot                 # per-lineage difference between operators
    L = pilot_cfg["evolution"]["lineages_per_model"]
    mde = 2.8 * sd_d / math.sqrt(2 * L)
    limit = 0.15 * pilot_cfg["tasks"]["partitions"]["sealed"]["n"]
    add("C5 noise", mde == mde and mde <= limit,
        f"gen-0 gain SD {sd_gain:.2f} tasks (scout) -> pilot minimum detectable S ~ {mde:.1f} tasks "
        f"(limit {limit:.0f})",
        "Raise audits.replicates_per_cell, cut presentations to [orig, norm], or add lineages -- "
        "or accept that the pilot can only detect a very large effect.")

    # C6 cost
    est = calibrated(pilot_sim_dir, pilot_cfg, prices, observed_profile(scout_dir, scout_cfg))
    id_to_key = {spec["model"]: k for k, spec in scout_cfg["models"].items()}
    spent_by = {}
    for r in spend:
        k = id_to_key.get(r["model"], "?")
        spent_by[k] = spent_by.get(k, 0.0) + r.get("usd", 0.0)
    if model_budgets:
        ok, parts = True, []
        for k, budget in model_budgets.items():
            proj = sum(l["usd"] for l in est["by_line"] if l["model"].startswith(f"{k} (")) * 1.5
            rem = budget - spent_by.get(k, 0.0)
            ok &= proj <= rem
            parts.append(f"{k}: projected ${proj / 1.5:.2f} (x1.5 ${proj:.2f}) vs remaining ${rem:.2f}")
        add("C6 cost", ok, "; ".join(parts),
            "Shrink the pilot (fewer lineages/generations) or load more credit with that vendor.")
    else:
        remaining = total_budget - spent
        add("C6 cost", est["total"]["x1.5"] <= remaining,
            f"pilot projected ${est['total']['x1']:.2f} (x1.5: ${est['total']['x1.5']:.2f}); remaining ${remaining:.2f}",
            "Shrink the pilot: fewer generations, K=2 continuations, or drop the 'neutral' presentation.")

    go = all(c["pass"] for c in checks)
    return {"decision": "GO" if go else "NO-GO", "scout_spent_usd": round(spent, 2), "checks": checks,
            "pilot_estimate": est, "note": "The scout's crossed matrix (2 lineages) is too small to interpret."}
