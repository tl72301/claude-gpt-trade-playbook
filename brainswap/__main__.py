"""The RSI Brain-Swap Test -- command line.

    python -m brainswap selftest                         normalizer + sandbox checks (no keys)
    python -m brainswap simulate --scenario all          SIMULATED pilot: null, presentation, content
    python -m brainswap simulate --scenario all --config demo_powered.yaml    SIMULATED powered study
    python -m brainswap budget --config pilot.yaml       cost estimate (needs a null simulation first)
    python -m brainswap demo                             site/brainswap_demo.html from simulations
    python -m brainswap preflight --config pilot.yaml    one real solver + improver call per model
    python -m brainswap calibrate --config pilot.yaml    seed solve rate by depth, per model (real)
    python -m brainswap scout                            stage 1 (real): prints GO / NO-GO
    python -m brainswap run --config pilot.yaml          stage 2: the pilot (resumable)
    python -m brainswap analyze --out runs_brainswap/pilot
    python -m brainswap extra --config pilot_v3_extra.yaml   follow-up: retry-only baseline + frozen lineages
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .experiment import ROOT, Experiment, load_config, seed_files

SIM_ROOT = ROOT / "runs_brainswap_mock"


def _analyze(out: Path, cfg: dict) -> dict:
    from .analysis import analyze, interpret, lineage_summary

    cells = [json.loads(p.read_text()) for p in sorted((out / "audits").glob("*/result.json"))]
    res = analyze(cells, list(cfg["models"]))
    lines = lineage_summary(out)
    res["lineages"] = lines
    res["verdicts"] = interpret(res, lines)
    spend = [json.loads(l) for l in (out / "spend.jsonl").read_text().splitlines() if l.strip()] \
        if (out / "spend.jsonl").exists() else []
    res["usage"] = {"calls": len(spend), "refusals": sum(r["refused"] for r in spend)}
    if spend and "usd" in spend[0]:   # the public copy has dollar figures removed
        by = {}
        for r in spend:
            k = r["purpose"].split(":")[0]
            by[k] = by.get(k, 0.0) + r["usd"]
        res["cost"] = {"total_usd": sum(r["usd"] for r in spend), "by_purpose": by}
    (out / "analysis.json").write_text(json.dumps(res, indent=1))
    return res


def _print(res: dict) -> None:
    for r in res["rows"]:
        ci = r.get("dS_ci")
        extra = f"  dS={r['dS']:+.2f} [{ci[0]:+.2f},{ci[1]:+.2f}]" if ci else ""
        print(f"  ckpt {r['checkpoint']:>2} {r['pres']:<9} S={r['S']:+.2f}{extra}")
    for v in res["verdicts"]:
        print("  -", v)
    if "cost" in res:
        print(f"  cost: ${res['cost']['total_usd']:.2f} over {res['usage']['calls']} calls")


def _scale(cfg: dict) -> str:
    n = cfg["name"]
    return "powered" if "powered" in n else "scout" if "scout" in n else "ci" if n.endswith("-ci") else "pilot"


def cmd_simulate(args):
    cfg = load_config(args.config)
    scenarios = ["null", "presentation", "content"] if args.scenario == "all" else [args.scenario]
    for sc in scenarios:
        out = Path(args.out or SIM_ROOT / _scale(cfg)) / sc
        print(f"== SIMULATED scenario '{sc}' -> {out}")
        Experiment(cfg, out, mock_scenario=sc, log=(print if args.verbose else lambda *_: None)).run()
        _print(_analyze(out, cfg))


def cmd_run(args):
    cfg = load_config(args.config)
    out = Path(args.out or ROOT / "runs_brainswap" / cfg["name"])
    Experiment(cfg, out).run()
    _print(_analyze(out, cfg))


def cmd_analyze(args):
    out = Path(args.out)
    cfg = load_config(args.config)
    _print(_analyze(out, cfg))


def cmd_budget(args):
    from rsi.config import load_config as rsi_cfg

    from .budget import calibrated, render

    cfg = load_config(args.config)
    sim = Path(args.calibration or SIM_ROOT / "pilot" / "null")
    if not (sim / "spend.jsonl").exists():
        sys.exit(f"No simulation at {sim}. Run: python -m brainswap simulate --scenario null "
                 f"--config {args.config} --out {sim.parent}")
    prices = rsi_cfg()["prices_usd_per_mtok"] | cfg.get("prices_usd_per_mtok", {})
    est = calibrated(sim, cfg, prices)
    print(f"Cost estimate for {cfg['name']} (call counts from {sim}):")
    print(render(est))
    print(f"Hard cap in config: ${cfg['limits']['max_usd_total']}")


def cmd_scout(args):
    """Stage 1: run the scout (real models unless --mock) and print GO / NO-GO."""
    from rsi.config import load_config as rsi_cfg

    from .scout import decide

    cfg = load_config(args.config)
    pilot = load_config(args.pilot)
    out = Path(args.out or (SIM_ROOT / "scout" / "null" if args.mock else ROOT / "runs_brainswap" / cfg["name"]))
    pilot_sim = Path(args.pilot_sim or SIM_ROOT / "pilot" / "null")
    if not (pilot_sim / "spend.jsonl").exists():
        print(f"No pilot simulation at {pilot_sim}; running one (mock, free) for call counts...")
        Experiment(load_config("demo.yaml"), pilot_sim, mock_scenario="null", log=lambda *_: None).run()
        _analyze(pilot_sim, load_config("demo.yaml"))
    if not (out / "cells.json").exists():
        Experiment(cfg, out, mock_scenario="null" if args.mock else None).run()
        _analyze(out, cfg)
    prices = rsi_cfg()["prices_usd_per_mtok"] | cfg.get("prices_usd_per_mtok", {})
    model_budgets = (dict(kv.split("=") for kv in args.model_budgets.split(",")) if args.model_budgets else None)
    if model_budgets:
        model_budgets = {k: float(v) for k, v in model_budgets.items()}
    res = decide(out, cfg, pilot, pilot_sim, prices, args.budget, seed_files()["improver.py"], model_budgets)
    (out / "scout_decision.json").write_text(json.dumps(res, indent=1))
    if args.mock:
        print("NOTE: --mock scout -- SIMULATED models; this decision means nothing about real models.")
    for c in res["checks"]:
        print(f"  [{'pass' if c['pass'] else 'FAIL'}] {c['criterion']}: {c['detail']}")
        if not c["pass"]:
            print(f"         -> {c['if_failed']}")
    print(f"Scout spent ${res['scout_spent_usd']:.2f}.  DECISION: {res['decision']}")
    return 0


def retry_only_solver(attempts: int) -> str:
    """The seed solver with its dormant check-and-retry loop switched on. Nothing else changes."""
    import re
    src = seed_files()["solver.py"]
    out, n1 = re.subn(r"^ATTEMPTS = 1$", f"ATTEMPTS = {attempts}", src, flags=re.M)
    out, n2 = re.subn(r"^USE_CHECK = False$", "USE_CHECK = True", out, flags=re.M)
    assert n1 == 1 and n2 == 1, "seed solver no longer has the expected switches"
    return out


def cmd_extra(args):
    """Follow-up run: retry-only baseline on the sealed set, then extra frozen lineages.
    Reuses the source pilot's tasks and sealed baselines so every number is comparable."""
    import shutil

    from .runtime import evaluate

    cfg = load_config(args.config)
    out = Path(args.out or ROOT / "runs_brainswap" / cfg["name"])
    src = ROOT / "runs_brainswap" / cfg["source_run"]
    out.mkdir(parents=True, exist_ok=True)
    for name in ("tasks.json", "sealed_baselines.json"):
        if not (out / name).exists():
            shutil.copy(src / name, out / name)
    exp = Experiment(cfg, out, mock_scenario="null" if args.mock else None)
    base = exp.sealed_baselines()

    # 1. Retry-only baseline.
    ro = cfg.get("retry_only", {})
    path = out / "retry_only.json"
    if path.exists():
        res = json.loads(path.read_text())
    else:
        solver = retry_only_solver(int(ro.get("attempts", 3)))
        (out / "retry_only_solver.py").write_text(solver)
        res = {}
        for key in exp.models:
            exp.spend.guard()
            led = exp.spend.new()
            scores = [evaluate(solver, exp.tasks["sealed"], exp.models[key], exp.sandbox, exp.run_cfg, led,
                               "sealed", f"retry_only:{key}:{r}")["n_passed"] for r in range(int(ro.get("repeats", 2)))]
            res[key] = {"scores": scores, "mean": sum(scores) / len(scores), "n": len(exp.tasks["sealed"]),
                        "seed_mean": base[key]["mean"], "gain": sum(scores) / len(scores) - base[key]["mean"],
                        "usd": led.usd}
        path.write_text(json.dumps(res, indent=1))
    for key, r in res.items():
        print(f"retry-only {key}: sealed {r['scores']} mean {r['mean']:g}/{r['n']} vs seed {r['seed_mean']:g} "
              f"-> gain {r['gain']:+.1f}")

    # 2. Extra frozen lineages (no evolution lineages, no audits in this config).
    lines = exp.evolve()
    (out / "lines.json").write_text(json.dumps(lines, indent=1))
    for s in lines:
        print(f"{s['group']}/{s['name']}: final dev bar {s['final_bar']:g}, accepted {s['accepted']}")
    return 0


def cmd_demo(args):
    from .demo import build

    path = build(Path(args.runs or SIM_ROOT), Path(args.out or ROOT / "site" / "brainswap_demo.html"))
    print("wrote", path)


def cmd_selftest(args):
    from .selftest import main as run_selftest
    return run_selftest()


def cmd_preflight(args):
    from rsi.config import load_config as rsi_cfg

    from .models import make_model
    from .runtime import Ledger, run_improver, evaluate
    from .tasks import generate
    from rsi.sandbox import Sandbox

    cfg = load_config(args.config)
    prices = rsi_cfg()["prices_usd_per_mtok"] | cfg.get("prices_usd_per_mtok", {})
    tasks = generate(3, [2, 3, 4], 99)
    sb = Sandbox("auto")
    run_cfg = dict(cfg["budgets"], workers=3)
    ok = True
    for key, spec in cfg["models"].items():
        model = make_model(spec, prices, mock_scenario=args.mock and "null", tasks={t.id: t for t in tasks})
        led = Ledger()
        ev = evaluate(seed_files()["solver.py"], tasks, model, sb, run_cfg, led, "preflight", "pf")
        ctx = {"generation": 1, "results": ev["results"], "memory": "", "budget": run_cfg["improver_budget"]}
        prop = run_improver(seed_files(), ctx, model, "orig", sb, run_cfg, tasks, led, "preflight", "pf")
        rows = led.rows
        report = {"model": spec["model"], "seed_solved": f"{ev['n_passed']}/{ev['n']}",
                  "improver_status": prop["status"], "files_returned": list(prop["files"]),
                  "refusals": sum(r["refused"] for r in rows), "mismatches": sum(r["mismatch"] for r in rows),
                  "served": sorted({str(r["served"]) for r in rows}),
                  "avg_out_tokens": {role: round(sum(r["out"] for r in rows if r["role"] == role) /
                                           max(1, sum(r["role"] == role for r in rows)))
                                     for role in ("solver", "improver")},
                  "usd": round(led.usd, 4)}
        print(json.dumps(report, indent=1))
        ok &= prop["status"] == "ok" and bool(prop["files"]) and not report["refusals"] and not report["mismatches"]
    print("preflight:", "OK" if ok else "PROBLEM -- see above")
    return 0 if ok else 1


def cmd_calibrate(args):
    from collections import defaultdict

    from rsi.config import load_config as rsi_cfg
    from rsi.sandbox import Sandbox

    from .models import make_model
    from .runtime import Ledger, evaluate
    from .tasks import generate

    cfg = load_config(args.config)
    prices = rsi_cfg()["prices_usd_per_mtok"] | cfg.get("prices_usd_per_mtok", {})
    tasks = generate(args.n, [2, 3, 4, 5], 4242)
    sb = Sandbox("auto")
    run_cfg = dict(cfg["budgets"], workers=cfg.get("workers", 8))
    for key, spec in cfg["models"].items():
        model = make_model(spec, prices, mock_scenario=args.mock and "null", tasks={t.id: t for t in tasks})
        led = Ledger()
        ev = evaluate(seed_files()["solver.py"], tasks, model, sb, run_cfg, led, "calibrate", "cal")
        by = defaultdict(lambda: [0, 0])
        for t, r in zip(tasks, ev["results"]):
            by[t.depth][0] += r["passed"]
            by[t.depth][1] += 1
        print(f"{key} {spec['model']}: " + "  ".join(f"depth {d}: {s}/{n}" for d, (s, n) in sorted(by.items()))
              + f"   (${led.usd:.3f})")
    print("Pick depths where BOTH models' seed solvers land roughly 25-65%, then set tasks.partitions.")


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m brainswap", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("simulate")
    s.add_argument("--scenario", default="null", choices=["null", "presentation", "content", "all"])
    s.add_argument("--config", default="demo.yaml")
    s.add_argument("--out")
    s.add_argument("--verbose", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--config", default="pilot.yaml")
    r.add_argument("--out")
    a = sub.add_parser("analyze")
    a.add_argument("--out", required=True)
    a.add_argument("--config", default="pilot.yaml")
    b = sub.add_parser("budget")
    b.add_argument("--config", default="pilot.yaml")
    b.add_argument("--calibration")
    d = sub.add_parser("demo")
    d.add_argument("--runs")
    d.add_argument("--out")
    sc = sub.add_parser("scout")
    sc.add_argument("--config", default="scout.yaml")
    sc.add_argument("--pilot", default="pilot.yaml")
    sc.add_argument("--pilot-sim")
    sc.add_argument("--budget", type=float, default=100.0, help="total budget in dollars, all stages")
    sc.add_argument("--model-budgets", default="",
                    help="per-vendor budgets, e.g. A=50,B=50 (overrides --budget for the cost check)")
    sc.add_argument("--out")
    sc.add_argument("--mock", action="store_true")
    sub.add_parser("selftest")
    ex = sub.add_parser("extra")
    ex.add_argument("--config", default="pilot_v3_extra.yaml")
    ex.add_argument("--out")
    ex.add_argument("--mock", action="store_true")
    pf = sub.add_parser("preflight")
    pf.add_argument("--config", default="pilot.yaml")
    pf.add_argument("--mock", action="store_true")
    c = sub.add_parser("calibrate")
    c.add_argument("--config", default="pilot.yaml")
    c.add_argument("--n", type=int, default=40)
    c.add_argument("--mock", action="store_true")
    args = p.parse_args(argv)
    handler = {"simulate": cmd_simulate, "run": cmd_run, "analyze": cmd_analyze, "budget": cmd_budget,
               "demo": cmd_demo, "selftest": cmd_selftest, "preflight": cmd_preflight, "scout": cmd_scout,
               "calibrate": cmd_calibrate, "extra": cmd_extra}[args.cmd]
    return handler(args) or 0


if __name__ == "__main__":
    sys.exit(main())
