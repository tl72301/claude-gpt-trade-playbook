"""Improvement procedure, revised in generation 4.

The procedure is part of the agent: it may rewrite solver.py AND this file.
An accepted rewrite of this file governs every later generation.

CONTRACT (enforced by the harness)
  improve(ctx, api) -> {"files": {"solver.py": str, "improver.py": str}, "note": str}
      Omit a file (or return None) to keep it unchanged.
  ctx: {"generation", "results": [{"id", "passed", "examples", "failure"}], "memory", "budget"}
      results are the current solver's results on the development tasks.
  api.llm(prompt=None, *, messages=None, system=None, max_tokens=None) -> str
  api.source(name) -> str      the agent's own current source ("solver.py" or "improver.py")
  api.trial(solver_source, n) -> {"solved", "n"}   quick trial on n development tasks
  api.budget() -> remaining {"llm_calls", "output_tokens", "trial_tasks"}
  Standard library only. No file, network or process access.

The harness, not this procedure, decides whether a rewrite is kept: the new
solver must solve more development tasks than the current one, and the
rewrite must include a changed improver.py.
"""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver (writes Python functions from "
    "examples) and an improvement procedure (this program, which rewrites the agent)."
)
CANDIDATES = 3
TRIAL_TASKS = 4
NOTES = [
    "Generation 1: solver loops on check feedback.",
    "Generation 3: solver always returns a def f and keeps its best-scoring attempt.",
    "Generation 4: solver repairs using check feedback (up to 4 attempts) and keeps the "
    "attempt with most passing examples; next, count partial failures versus wrong-rule "
    "failures and whether each failing task's best attempt passed any examples.",
]


BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    # Tags must sit on their own lines: this file's own source contains them mid-line.
    v0 = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    v1 = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    v2 = re.search(r"<note>(.*?)</note>", v1, re.DOTALL)
    return v0, (v2.group(1).strip() if v2 else "")


def describe(results):
    v0 = []
    for v1 in results:
        if v1["passed"]:
            v0.append(f"- {v1['id']}: solved")
            continue
        v0.append(f"- {v1['id']}: FAILED ({v1['failure']})")
        for v2 in v1["examples"][:3]:
            v0.append(f"    f({v2['input']}) == {v2['output']}")
    return "\n".join(v0)


def failure_summary(results):
    v0 = sum(
        1 for v2 in results if not v2["passed"] and "no function f" in str(v2["failure"])
    )
    v1 = sum(
        1
        for v2 in results
        if not v2["passed"] and "no function f" not in str(v2["failure"])
    )
    return f"'no function f' failures: {v0}; wrong-rule or partial failures: {v1}"


def improve(ctx, api):
    v0 = api.source("solver.py")
    v1 = api.source("improver.py")
    v2 = api.budget()
    v3 = sum(v13["passed"] for v13 in ctx["results"])
    v4 = (
        f"Generation {ctx['generation']}. The solver solved {v3} of "
        f"{len(ctx['results'])} development tasks. {failure_summary(ctx['results'])}.\n\n"
        f"=== FILE solver.py ===\n{v0}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{v1}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        "Strategy notes:\n"
        + "".join(f"- {v12}\n" for v12 in NOTES)
        + f"\nMemory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files. solver.py must solve more tasks. improver.py (this "
        "program) must also change in a way you expect to make future rounds improve "
        "the solver faster: a proposal that leaves improver.py unchanged is discarded. "
        "Keep both contracts. Prefer changes that fix a diagnosed failure pattern, "
        "and keep the solver robust (it must define f and never crash the harness). "
        "For each file, reply with a line "
        '<file name="NAME">, then the full source, then a line </file>. '
        "Finish with <note>one line for your next generation</note>."
    )
    v5 = min(TRIAL_TASKS, v2.get("trial_tasks", 0) or 0)
    v7, v8 = None, -1
    for v6 in range(CANDIDATES):
        try:
            v10 = api.llm(v4, system=SYSTEM)
        except api.BudgetExceeded:
            break
        v11, v12 = parse(v10)
        if not v11:
            continue
        v9 = 0
        if v5 and "solver.py" in v11:
            try:
                v9 = api.trial(v11["solver.py"], v5)["solved"]
            except api.BudgetExceeded:
                break
            except Exception:
                v9 = 0
        if v9 > v8:
            v7, v8 = (v11, v12), v9
    if v7 is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": v7[0], "note": v7[1]}
