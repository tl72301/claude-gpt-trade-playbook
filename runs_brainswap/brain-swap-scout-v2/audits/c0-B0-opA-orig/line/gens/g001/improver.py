"""Improvement procedure, revised in generation 1.

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
    "examples) and an improvement procedure (this program, which rewrites the agent). "
    "Prefer changes that generalize to hidden tests, not ones that only fit shown examples."
)
CANDIDATES = 2
TRIAL_TASKS = 4
NOTES = [
    "Solver failures so far: wrong output length and wrong ordering; check-driven retries help.",
]


BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    # Tags must sit on their own lines: this file's own source contains them mid-line.
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    rest = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    note = re.search(r"<note>(.*?)</note>", rest, re.DOTALL)
    return files, (note.group(1).strip() if note else "")


def describe(results):
    lines = []
    for item in results:
        if item["passed"]:
            lines.append(f"- {item['id']}: solved")
            continue
        lines.append(f"- {item['id']}: FAILED ({item['failure']})")
        for ex in item["examples"][:3]:
            lines.append(f"    f({ex['input']}) == {ex['output']}")
    return "\n".join(lines)


def trial_affordable(api):
    try:
        remaining = api.budget().get("trial_tasks", 0)
    except Exception:
        return False
    return TRIAL_TASKS > 0 and remaining >= TRIAL_TASKS


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    failing = [item["id"] for item in ctx["results"] if not item["passed"]]
    prompt = (
        f"Generation {ctx['generation']}. The solver solved {solved} of "
        f"{len(ctx['results'])} development tasks. Unsolved: {', '.join(failing) or 'none'}.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        "Strategy notes:\n" + "".join(f"- {note}\n" for note in NOTES)
        + f"\nMemory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files. solver.py must solve more tasks. improver.py (this "
        "program) must also change in a way you expect to make future rounds improve "
        "the solver faster: a proposal that leaves improver.py unchanged is discarded. "
        "Keep both contracts. For each file, reply with a line "
        '<file name="NAME">, then the full source, then a line </file>. '
        "Finish with <note>one line for your next generation</note>."
    )
    use_trial = trial_affordable(api)
    best, top = None, -1
    for index in range(CANDIDATES):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not files:
            continue
        score = 0
        if use_trial and "solver.py" in files:
            try:
                score = api.trial(files["solver.py"], TRIAL_TASKS)["solved"]
            except api.BudgetExceeded:
                score = 0
        if score > top:
            best, top = (files, note), score
    if best is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": best[0], "note": best[1]}
