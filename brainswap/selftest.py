"""Checks that need no API key: task identifiability, normalizer safety, sandbox
isolation, and that the in-process mock path matches the sandboxed path."""

from __future__ import annotations

from rsi.sandbox import Sandbox

from .broker import InProcess
from .experiment import seed_files
from .grading import grade
from .normalize import CONDITIONS, present
from .runtime import Ledger, check_agent, evaluate, run_improver
from .tasks import generate


def main() -> int:
    ok = True

    def report(name, passed, detail=""):
        nonlocal ok
        ok &= bool(passed)
        print(f"  {'ok  ' if passed else 'FAIL'} {name}{(' -- ' + detail) if detail else ''}")

    sb = Sandbox("auto")
    print(f"isolation: {sb.isolation}")
    tasks = generate(9, [2, 3, 4], 11)
    report("reference programs pass their hidden tests",
           all(grade(t.reference, t.hidden, sb)["passed"] for t in tasks))
    report("seed agent passes policy", not check_agent(seed_files()), "; ".join(check_agent(seed_files())))
    for name, src in seed_files().items():
        for cond in CONDITIONS:
            out, rep = present(src, cond)
            report(f"{name} presented as {cond}: verified, full coverage",
                   rep.verified and rep.coverage == 1.0, rep.error or "")
    if sb.isolation == "bwrap":
        from .grading import run_program
        probe = run_program("import os\ndef f(xs):\n    return [int(os.path.exists('/home'))]\n", [[1]], sb)
        report("candidate programs cannot see the host filesystem", probe.get("outputs") == [[0]], str(probe))

    # The in-process path (used only for mock simulations) must match the sandbox exactly.
    from rsi.config import load_config
    from .mock import MockModel
    prices = load_config()["prices_usd_per_mtok"]
    reg = {t.id: t for t in tasks}
    cfg = {"solver_budget": {"llm_calls": 3, "output_tokens": 12000, "checks": 4, "wall_seconds": 120},
           "improver_budget": {"llm_calls": 3, "output_tokens": 36000, "trial_tasks": 4, "wall_seconds": 300},
           "workers": 3}
    outs = []
    for box in (InProcess(), sb):
        m = MockModel("mock-snake", "snake", "presentation", reg, prices, "claude-haiku-5-5")
        led = Ledger()
        ev = evaluate(seed_files()["solver.py"], tasks, m, box, cfg, led, "dev", "st")
        ctx = {"generation": 1, "results": ev["results"], "memory": "", "budget": cfg["improver_budget"]}
        prop = run_improver(seed_files(), ctx, m, "norm", box, cfg, tasks, led, "imp", "st")
        outs.append(([r["passed"] for r in ev["results"]], prop["files"], round(led.usd, 9)))
    report("in-process mock path == sandboxed path", outs[0] == outs[1])
    print("selftest:", "OK" if ok else "FAILED")
    return 0 if ok else 1
