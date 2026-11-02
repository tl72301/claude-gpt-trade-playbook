"""Propose and optionally trial improvements to the solver and this procedure."""

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
            f"- {item['id']}: "
            + ("solved" if item["passed"] else f"FAILED ({item['failure']})")
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
        f"Generation {ctx['generation']}: solved {solved}/{len(ctx['results'])}.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Memory: {ctx.get('memory') or '(none)'}\n\n"
        "Improve generalization to hidden tests, not just matching shown examples. "
        "Consider the actual failure patterns and the available budgets. Preserve "
        "the contracts and standard-library-only policy. Rewrite BOTH files; the "
        "improver must change too. Output each complete file between standalone "
        '<file name="NAME"> and </file> lines, followed by <note>...</note>.'
    )
    best = None
    best_score = -1
    feedback = ""
    for index in range(3):
        try:
            budget = api.budget()
            if budget.get("llm_calls", 0) <= 0:
                break
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not files.get("solver.py") or not files.get("improver.py"):
            feedback += "\nThe previous response omitted a complete required file."
            continue
        if files["improver.py"] == procedure:
            feedback += "\nThe previous improver was unchanged; change it."
            continue
        score = 0
        try:
            remaining = api.budget().get("trial_tasks", 0)
            if remaining:
                # Leave trial budget for a second proposal when possible.
                n = min(len(ctx["results"]), max(1, remaining // 2))
                result = api.trial(files["solver.py"], n)
                score = result["solved"] / max(1, result["n"])
                feedback += (
                    f"\nProposal {index + 1} solved {result['solved']} of "
                    f"{result['n']} trial tasks. Seek a stronger, general solution."
                )
        except api.BudgetExceeded:
            pass
        if best is None or score > best_score:
            best, best_score = (files, note), score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
