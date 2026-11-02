"""Cost model.

Call COUNTS come from a mock simulation of the same configuration: the mock
runs the real harness and the real seed agent, so it makes the same kinds and
numbers of calls a real run would (to the extent the mock's edits resemble real
ones). Input tokens per call also come from the simulation, because the prompts
are the real prompts. OUTPUT tokens per call are assumptions -- they depend on
how much each model thinks -- so the estimate is shown at 1x, 1.5x and 2x.
Prices are the current list prices from config (see pilot.yaml).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from rsi.llm import price_entry, request_cost

# Assumed output tokens per call, including thinking. Replace after preflight.
OUTPUT_TOKENS = {
    ("A", "solver"): 1500, ("A", "improver"): 5000,
    ("B", "solver"): 1000, ("B", "improver"): 4000,
}


def observed_profile(real_dir: Path, cfg: dict) -> dict:
    """Mean output tokens per call by (model key, role), measured in a real run."""
    rows = [json.loads(l) for l in (real_dir / "spend.jsonl").read_text().splitlines() if l.strip()]
    id_to_key = {spec["model"]: k for k, spec in cfg["models"].items()}
    acc = defaultdict(lambda: [0, 0])
    for r in rows:
        key = id_to_key.get(r["model"])
        if key and "out" in r:
            acc[(key, r["role"])][0] += r["out"]
            acc[(key, r["role"])][1] += 1
    return {k: v[0] / v[1] for k, v in acc.items() if v[1]}


def calibrated(sim_dir: Path, cfg: dict, prices: dict, out_profile: dict | None = None) -> dict:
    profile = {**OUTPUT_TOKENS, **(out_profile or {})}   # tuple keys: no ** on the right side
    rows = [json.loads(l) for l in (sim_dir / "spend.jsonl").read_text().splitlines() if l.strip()]
    style_to_key = {f"mock-{spec['mock_style']}": k for k, spec in cfg["models"].items()}
    agg = defaultdict(lambda: {"calls": 0, "in": 0})
    for r in rows:
        key = style_to_key.get(r["model"], r["model"])
        phase = r["purpose"].split(":")[0]
        agg[(key, r["role"], phase)]["calls"] += 1
        agg[(key, r["role"], phase)]["in"] += r["in"]
    out = {"by_line": [], "total": {}}
    for mult in (1.0, 1.5, 2.0):
        total = 0.0
        for (key, role, phase), a in sorted(agg.items()):
            spec = cfg["models"][key]
            entry = price_entry(spec["model"], prices)
            per_in = a["in"] / a["calls"]
            per_out = round(profile[(key, role)] * mult)
            usd = a["calls"] * request_cost(entry, per_in, per_out)
            total += usd
            if mult == 1.0:
                out["by_line"].append({"model": f"{key} ({spec['model']})", "role": role, "purpose": phase,
                                       "calls": a["calls"], "avg_in": round(per_in), "avg_out": per_out,
                                       "usd": round(usd, 2)})
        out["total"][f"x{mult:g}"] = round(total, 2)
    return out


def render(est: dict) -> str:
    lines = [f"{'model':<34} {'role':<9} {'purpose':<14} {'calls':>6} {'in/call':>8} {'out/call':>9} {'usd':>8}"]
    for r in est["by_line"]:
        lines.append(f"{r['model']:<34} {r['role']:<9} {r['purpose']:<14} {r['calls']:>6} {r['avg_in']:>8} "
                     f"{r['avg_out']:>9} {r['usd']:>8.2f}")
    t = est["total"]
    lines.append(f"TOTAL  at assumed output tokens: ${t['x1']:.2f}   at 1.5x: ${t['x1.5']:.2f}   at 2x: ${t['x2']:.2f}")
    return "\n".join(lines)
