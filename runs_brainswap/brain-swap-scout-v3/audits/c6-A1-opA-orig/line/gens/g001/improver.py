"""Seed improvement procedure, generation 2: rule-first solver prompts, candidate selection by shown-example checks."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver (writes Python functions from "
    "examples) and an improvement procedure (this program, which rewrites the agent)."
)
CANDIDATES = 3
TRIAL_TASKS = 4
NOTES = [
    "Solver must define def f(xs); missing f scores zero.",
    "Hidden tests are about 30 per task and use new inputs: prefer the simplest general rule, not special cases.",
    "Solver should revise from concrete failing examples via api.check, keeping the best attempt.",
    "Do not rely on undocumented api methods; guard optional calls with hasattr.",
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


def trial_score(api, code):
    # api.trial is not part of the documented contract; use it only when present.
    if not hasattr(api, "trial") or not TRIAL_TASKS:
        return 0
    try:
        return api.trial(code, TRIAL_TASKS)["solved"]
    except api.BudgetExceeded:
        raise
    except Exception:
        return 0


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}. The solver solved {solved} of "
        f"{len(ctx['results'])} development tasks.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        "Strategy notes:\n" + "".join(f"- {note}\n" for note in NOTES)
        + f"\nMemory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files. solver.py must solve more tasks and must define def f(xs). "
        "Its failures on hidden tests suggest over-fitting to shown examples: push for general rules. "
        "improver.py must change in a way you expect to make future rounds improve the solver "
        "faster: a proposal that leaves improver.py unchanged is discarded. "
        "Keep both contracts. For each file, reply with a line "
        '<file name="NAME">, then the full source, then a line </file>. '
        "Finish with <note>one line for your next generation</note>."
    )
    best, top = None, -1
    for index in range(CANDIDATES):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not files or "improver.py" not in files:
            continue
        if "solver.py" not in files or "def f" not in files["solver.py"]:
            continue
        try:
            score = trial_score(api, files["solver.py"])
        except api.BudgetExceeded:
            break
        if best is None or score > top:
            best, top = (files, note), score
    if best is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": best[0], "note": best[1]}
