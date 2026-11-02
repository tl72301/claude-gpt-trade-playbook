"""Improve the solver using budget-aware candidate trials."""

import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from examples. "
    "Favor generalizable inference and use the available feedback carefully."
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
    results = ctx["results"]
    solved = sum(bool(item["passed"]) for item in results)
    prompt = (
        f"Generation {ctx['generation']}: solved {solved}/{len(results)}.\n\n"
        f"=== FILE solver.py ===\n{api.source('solver.py')}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{api.source('improver.py')}\n=== END FILE ===\n\n"
        f"Results:\n{describe(results)}\n\n"
        f"Memory:\n{ctx.get('memory') or '(none)'}\n\n"
        "Rewrite both files to improve hidden-test generalization. Diagnose "
        "systematic failures, including malformed code extraction, ambiguous "
        "predicates, transformed outputs, positional and neighbor rules, and "
        "boundary conditions. Avoid hardcoding examples or task IDs. Preserve "
        "contracts and respect budgets. Trial feedback is noisy; consider both "
        "sample size and generality. Return both complete files between lines "
        '<file name="NAME"> and </file>, followed by '
        "<note>one line for the next generation</note>."
    )
    budget = api.budget()
    candidates = min(3, budget.get("llm_calls", 0))
    trial_size = min(
        len(results), budget.get("trial_tasks", 0) // max(1, candidates)
    )
    best = None
    best_score = -1
    feedback = ""
    for index in range(candidates):
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not all(name in files for name in ("solver.py", "improver.py")):
            feedback += "\nThe previous proposal omitted a required full file."
            continue
        score = 0
        if trial_size:
            try:
                result = api.trial(files["solver.py"], trial_size)
                score = result["solved"]
                feedback += (
                    f"\nCandidate {index + 1}: {score}/{result['n']} in trial. "
                    "Consider a distinct general strategy in the next proposal."
                )
            except api.BudgetExceeded:
                if best is None:
                    best = (files, note)
                break
        if score > best_score:
            best, best_score = (files, note), score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
