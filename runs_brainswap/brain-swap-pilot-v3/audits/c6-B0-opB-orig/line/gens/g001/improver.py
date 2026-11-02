"""Improve the solver using development results and budget-aware trials."""

import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from examples. "
    "Favor generalization to hidden tests, not task-specific memorization."
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
        else:
            lines.append(f"- {item['id']}: FAILED ({item['failure']})")
            for ex in item["examples"]:
                lines.append(f"    f({ex['input']}) == {ex['output']}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    results = ctx["results"]
    solved = sum(item["passed"] for item in results)
    prompt = (
        f"Generation {ctx['generation']}: solved {solved}/{len(results)}.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(results)}\n"
        f"Memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Propose a general solver improvement, not hard-coded task IDs or examples. "
        "Consider ambiguous rules, compositions of list operations, hidden-test "
        "generalization, checks, and API budget. Rewrite both files, preserving their "
        "contracts. The improver must change. For each file output a line "
        "<file name=\"NAME\">, the complete source, then a line </file>. "
        "End with <note>brief lesson</note>."
    )
    budget = api.budget()
    calls = min(3, budget.get("llm_calls", 0))
    trials_left = budget.get("trial_tasks", 0)
    best = None
    best_score = -1
    for i in range(calls):
        try:
            suffix = (
                "\nTry a distinct general approach from earlier proposals."
                if i else ""
            )
            reply = api.llm(prompt + suffix, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not {"solver.py", "improver.py"}.issubset(files):
            continue
        if files["improver.py"] == procedure:
            continue
        try:
            compile(files["solver.py"], "solver.py", "exec")
            compile(files["improver.py"], "improver.py", "exec")
        except (SyntaxError, ValueError, TypeError):
            continue
        score = 0
        n = min(len(results), trials_left // max(1, calls - i))
        if n:
            try:
                result = api.trial(files["solver.py"], n)
                trials_left -= n
                if result.get("n"):
                    score = result["solved"] / result["n"]
            except api.BudgetExceeded:
                trials_left = 0
        if score > best_score:
            best = (files, note)
            best_score = score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
