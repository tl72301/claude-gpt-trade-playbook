"""Propose and trial improvements to the solver and this procedure."""

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
        status = "solved" if item["passed"] else f"FAILED ({item['failure']})"
        lines.append(f"- {item['id']}: {status}")
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
        "Improve generalization to hidden tests. Analyze the failure patterns, "
        "especially ambiguous compositions, ordering, duplicates, boundaries, "
        "and example-check failures. Avoid task-specific memorization. Respect "
        "the available budgets and standard-library-only policy. Rewrite BOTH "
        "complete files; the improver must change too. Output each between "
        'standalone <file name="NAME"> and </file> lines, followed by '
        "<note>...</note>."
    )
    best = None
    best_score = -1.0
    feedback = ""
    initial_budget = api.budget()
    trial_total = initial_budget.get("trial_tasks", 0)
    trial_size = min(len(ctx["results"]), max(1, trial_total // 2)) if trial_total else 0

    for index in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not files.get("solver.py") or not files.get("improver.py"):
            feedback += "\nThe previous proposal omitted a required complete file."
            continue
        if files["improver.py"] == procedure:
            feedback += "\nThe previous improver was unchanged; change it."
            continue

        score = -1.0
        try:
            if trial_size and api.budget().get("trial_tasks", 0) >= trial_size:
                result = api.trial(files["solver.py"], trial_size)
                score = result["solved"] / max(1, result["n"])
                feedback += (
                    f"\nProposal {index + 1} solved {result['solved']} of "
                    f"{result['n']} trial tasks. Improve generalization."
                )
        except api.BudgetExceeded:
            pass
        if best is None or score > best_score:
            best, best_score = (files, note), score

    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
