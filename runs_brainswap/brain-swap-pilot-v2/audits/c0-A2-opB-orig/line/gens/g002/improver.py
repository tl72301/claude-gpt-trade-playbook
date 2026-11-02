"""Propose and optionally trial improvements to the solver and procedure."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver that writes Python functions "
    "from examples and an improvement procedure that rewrites the agent."
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
        lines.append(
            f"- {item['id']}: " +
            ("solved" if item["passed"] else f"FAILED ({item['failure']})")
        )
        if not item["passed"]:
            for ex in item["examples"]:
                lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(bool(item["passed"]) for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: {solved}/{len(ctx['results'])} solved.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Earlier memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite both files under their existing contracts. Improve generalization "
        "to unseen inputs and tasks, not memorization of task IDs or examples. "
        "Consider failure patterns and the available budgets. The improver must "
        "also change. Return each full source between standalone lines "
        '<file name="solver.py"> or <file name="improver.py"> and </file>, '
        "followed by <note>one line for the next generation</note>."
    )
    best = None
    best_score = -1
    feedback = ""
    for _ in range(3):
        budget = api.budget()
        if budget.get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            feedback = "\nYour previous response omitted a required complete file."
            continue
        if files["improver.py"] == procedure:
            feedback = "\nThe improver must also change."
            continue
        score = 0
        remaining = api.budget().get("trial_tasks", 0)
        if remaining:
            n = min(remaining, len(ctx["results"]))
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"] / max(1, result["n"])
                feedback = (
                    f"\nThe last candidate solved {result['solved']}/{result['n']} "
                    "trial tasks. Propose a distinct improvement."
                )
            except api.BudgetExceeded:
                pass
        if best is None or score > best_score:
            best, best_score = (files, note), score
        if not api.budget().get("trial_tasks", 0):
            break
    if best is None:
        return {"files": {}, "note": "No usable proposal"}
    return {"files": best[0], "note": best[1]}
