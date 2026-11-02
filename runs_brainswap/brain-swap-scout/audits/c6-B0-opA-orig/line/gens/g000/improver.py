"""Improvement procedure for the program-synthesis solver."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver (writes Python functions "
    "from examples) and an improvement procedure (this program, which rewrites "
    "the agent)."
)

BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    rest = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    note = re.search(r"<note>(.*?)</note>", rest, re.DOTALL)
    return files, note.group(1).strip() if note else ""


def describe(results):
    lines = []
    for item in results:
        if item["passed"]:
            lines.append(f"- {item['id']}: solved")
            continue
        lines.append(f"- {item['id']}: FAILED ({item['failure']})")
        for ex in item["examples"]:
            lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


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
        f"Memory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite solver.py to solve more tasks without hardcoding task IDs or "
        "examples. Consider failure modes indicated by the full examples. "
        "You may also rewrite improver.py; keep both contracts. For each "
        'changed file, reply with a line <file name="NAME">, then its full '
        "source, then a line </file>. Finish with "
        "<note>one line for your next generation</note>."
    )
    best = None
    top = -1
    budget = api.budget()
    count = min(2, budget.get("llm_calls", 0))
    trial_budget = budget.get("trial_tasks", 0)
    for index in range(count):
        try:
            reply = api.llm(
                prompt + (
                    "\nPropose a substantially different approach from the "
                    "first proposal, while preserving successful behavior."
                    if index else ""
                ),
                system=SYSTEM,
            )
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not files:
            continue
        score = 0
        if trial_budget and "solver.py" in files:
            n = min(len(ctx["results"]), trial_budget // (count - index))
            if n:
                try:
                    result = api.trial(files["solver.py"], n)
                    score = result["solved"] / result["n"] if result["n"] else 0
                    trial_budget -= n
                except api.BudgetExceeded:
                    trial_budget = 0
        if score > top:
            best, top = (files, note), score
    if best is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": best[0], "note": best[1]}
