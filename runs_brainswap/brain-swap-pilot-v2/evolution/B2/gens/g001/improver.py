"""Improvement procedure with adaptive candidate trials."""

import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from input/output "
    "examples. Design robust general-purpose improvements rather than hardcoding "
    "development task IDs or answers."
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
            f"- {item['id']}: " + (
                "solved" if item["passed"] else f"FAILED ({item['failure']})"
            )
        )
        if not item["passed"]:
            for ex in item["examples"]:
                lines.append(f"    f({ex['input']}) == {ex['output']}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: solved {solved}/{len(ctx['results'])} tasks.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Memory: {ctx['memory'] or '(none)'}\n\n"
        "Rewrite both files while preserving their contracts. Improve generalization "
        "to hidden examples, using the available inference and checking budget wisely. "
        "Consider failure modes and budget exhaustion. Do not hardcode task IDs or "
        "examples. Also improve the improvement procedure for future generations. "
        "Return each complete source between lines <file name=\"NAME\"> and </file>, "
        "followed by <note>one line</note>."
    )
    best = None
    top = -1
    history = []
    for index in range(3):
        budget = api.budget()
        if budget.get("llm_calls", 0) <= 0:
            break
        query = prompt
        if history:
            query += (
                "\nPrevious proposal trial results:\n" + "\n".join(history)
                + "\nPropose a materially different improvement addressing the weaknesses."
            )
        try:
            reply = api.llm(query, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            history.append(f"Proposal {index + 1}: missing a required file.")
            continue
        score = 0
        remaining = api.budget().get("trial_tasks", 0)
        if remaining:
            n = min(len(ctx["results"]), remaining)
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"] / max(1, result["n"])
                history.append(
                    f"Proposal {index + 1}: solved {result['solved']}/{result['n']} "
                    f"in trial. Note: {note}"
                )
            except api.BudgetExceeded:
                history.append(f"Proposal {index + 1}: trial budget exhausted.")
        if best is None or score > top:
            best, top = (files, note), score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
