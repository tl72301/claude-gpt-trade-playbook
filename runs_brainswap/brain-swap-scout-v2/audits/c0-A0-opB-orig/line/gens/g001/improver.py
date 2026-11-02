"""Propose and, when budget permits, trial improvements to the solver."""
import re

SYSTEM = (
    "You improve an AI agent that writes Python functions from examples. "
    "Preserve the contracts and propose generalizable changes."
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
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: solved {solved}/{len(ctx['results'])}.\n"
        f"=== solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Memory: {ctx['memory'] or '(none)'}\n"
        "Improve generalization to hidden tests, not just shown examples. "
        "Consider ambiguity, boundary cases, checking, and available budgets. "
        "Rewrite both files, preserving their contracts. The improver must change. "
        "Return each complete file between lines <file name=\"NAME\"> and </file>, "
        "then <note>one line for the next generation</note>."
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
            feedback += "\nThe previous proposal omitted a required complete file."
            continue
        if files["improver.py"] == procedure:
            feedback += "\nThe previous proposal did not change improver.py."
            continue
        score = 0
        remaining = api.budget().get("trial_tasks", 0)
        n = len(ctx["results"])
        if remaining >= n and n:
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"]
                feedback += (
                    f"\nProposal {index + 1} trial: {score}/{result['n']} solved. "
                    "Try a different approach if this is not an improvement."
                )
            except api.BudgetExceeded:
                pass
        if best is None or score > best_score:
            best, best_score = (files, note), score
        if score > solved:
            break
        if remaining < n:
            break
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
