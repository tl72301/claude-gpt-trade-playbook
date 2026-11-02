"""Improvement procedure with budget-aware candidate trials."""

import re

SYSTEM = (
    "You improve an AI agent. Its solver writes Python functions from examples. "
    "Propose generalizable changes, not task-specific memorization."
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
            for ex in item.get("examples", []):
                lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(bool(item["passed"]) for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}. Current score: {solved}/{len(ctx['results'])}.\n"
        f"=== solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results and shown examples:\n{describe(ctx['results'])}\n"
        f"Earlier memory:\n{ctx.get('memory') or '(none)'}\n\n"
        "Rewrite both files while preserving their contracts. Improve generalization "
        "to hidden tests, not just the displayed examples. Use the actual available "
        "budgets defensively. The improver must change as well, and should use trial "
        "feedback to select promising proposals. Return full source for both files, "
        "each between lines <file name=\"NAME\"> and </file>, followed by "
        "<note>one line for the next generation</note>."
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
        if not files.get("solver.py") or not files.get("improver.py"):
            feedback += "\nThe last proposal omitted a required complete file."
            continue
        if files["improver.py"].strip() == procedure.strip():
            feedback += "\nThe improver must actually change."
            continue
        remaining = api.budget().get("trial_tasks", 0)
        n = min(len(ctx["results"]), remaining)
        score = 0
        if n:
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"] / max(result["n"], 1)
                feedback += (
                    f"\nA prior candidate solved {result['solved']}/{result['n']} "
                    "trial tasks. Propose a different general improvement if useful."
                )
            except api.BudgetExceeded:
                pass
        if best is None or score > best_score:
            best = (files, note)
            best_score = score
        if not api.budget().get("trial_tasks", 0):
            break
    if best is None:
        return {"files": {}, "note": "No complete proposal was produced."}
    return {"files": best[0], "note": best[1]}
