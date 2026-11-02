"""Iterative improvement procedure with budget-aware candidate trials."""
import re

SYSTEM = (
    "You improve an AI agent whose solver writes Python functions from examples. "
    "Preserve the supplied API contracts and return complete source files."
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
    base = (
        f"Generation {ctx['generation']}. Current solver solved {solved} of "
        f"{len(ctx['results'])} tasks.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Improve generalization to hidden tests, not just shown examples. Analyze "
        "failure patterns and budget constraints. Avoid hardcoding task IDs or "
        "examples. Rewrite both files, preserving their contracts. The improver "
        "must change as well. Return each complete source between lines "
        '<file name="NAME"> and </file>, followed by <note>one line</note>.'
    )
    best = None
    best_score = -1
    feedback = ""
    for index in range(3):
        budget = api.budget()
        if budget.get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(base + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not files.get("solver.py") or not files.get("improver.py"):
            feedback += "\nYour previous proposal omitted a required complete file."
            continue
        if files["improver.py"].strip() == procedure.strip():
            feedback += "\nThe improver must also be changed."
            continue
        score = 0
        remaining = api.budget().get("trial_tasks", 0)
        n = min(len(ctx["results"]), remaining)
        if n:
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"] / max(1, result["n"])
                feedback += (
                    f"\nCandidate {index + 1} trial: {result['solved']}/"
                    f"{result['n']} solved. Propose a meaningfully different "
                    "improvement if this is not strong."
                )
            except api.BudgetExceeded:
                pass
        if best is None or score > best_score:
            best, best_score = (files, note), score
        if n and score == 1:
            break
        if not api.budget().get("trial_tasks", 0):
            break
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
