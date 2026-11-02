"""Improvement procedure: propose and, when possible, trial multiple rewrites."""

import re

SYSTEM = (
    "You improve an AI agent that writes Python functions from examples. "
    "Preserve both API contracts and favor generalization over task-specific memorization."
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
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: solved {solved}/{len(ctx['results'])}.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory: {ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files, preserving their contracts. Improve solver performance "
        "on hidden tests, not merely shown examples. The improver must also change; "
        "make its future search and evaluation more effective. Respect available API "
        "budgets and use only the standard library. Return each complete source between "
        'standalone <file name="NAME"> and </file> lines, followed by '
        "<note>one line for the next generation</note>."
    )
    best = None
    best_score = -1
    feedback = ""
    for index in range(3):
        budget = api.budget()
        if budget.get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            feedback = "\nThe previous proposal omitted a required file. Return both."
            continue
        if files["improver.py"] == procedure:
            feedback = "\nThe previous improver was unchanged. Change it as well."
            continue
        score = 0
        remaining = api.budget().get("trial_tasks", 0)
        if remaining:
            # Use a consistent sample size across candidates when the budget permits.
            n = min(len(ctx["results"]), remaining, max(1, ctx["budget"].get("trial_tasks", remaining) // 3))
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"] / max(1, result["n"])
                feedback = (
                    f"\nA previous candidate solved {result['solved']}/{result['n']} "
                    "trial tasks. Propose a distinct, general improvement."
                )
            except api.BudgetExceeded:
                pass
        if best is None or score > best_score:
            best, best_score = (files, note), score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
