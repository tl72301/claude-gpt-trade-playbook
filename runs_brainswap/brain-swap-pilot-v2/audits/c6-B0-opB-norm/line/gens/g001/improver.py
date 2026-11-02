"""Budget-aware improvement procedure."""

import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from examples. "
    "Favor generalizable inference and use the available feedback carefully."
)
BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    remainder = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    note = re.search(r"<note>(.*?)</note>", remainder, re.DOTALL)
    return files, note.group(1).strip() if note else ""


def describe(results):
    lines = []
    for result in results:
        lines.append(
            f"- {result['id']}: "
            + ("solved" if result["passed"] else f"FAILED ({result['failure']})")
        )
        if not result["passed"]:
            for example in result["examples"]:
                lines.append(
                    f"    f({example['input']!r}) == {example['output']!r}"
                )
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    improver = api.source("improver.py")
    solved = sum(bool(result["passed"]) for result in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: solved {solved}/{len(ctx['results'])}.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{improver}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory:\n{ctx.get('memory') or '(none)'}\n\n"
        "Rewrite both files to improve generalization to hidden tests. Diagnose "
        "systematic failure modes, especially ambiguous boundaries, ordering, "
        "duplicates, indices versus values, and relationships between elements. "
        "Do not hard-code task IDs or individual examples. Preserve the contracts "
        "and respect API budgets. The improver must change too. Return each full "
        'file between lines <file name="NAME"> and </file>, followed by '
        "<note>one line for the next generation</note>."
    )
    budget = api.budget()
    attempts = min(3, budget.get("llm_calls", 0))
    trial_size = min(
        len(ctx["results"]),
        budget.get("trial_tasks", 0) // max(1, attempts),
    )
    best = None
    best_score = -1
    feedback = ""
    for index in range(attempts):
        try:
            response = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(response)
        if "solver.py" not in files or "improver.py" not in files:
            feedback += "\nThe previous proposal omitted a required full file."
            continue
        score = 0
        if trial_size:
            try:
                trial = api.trial(files["solver.py"], trial_size)
            except api.BudgetExceeded:
                trial = None
            if trial is not None:
                score = trial["solved"]
                feedback += (
                    f"\nCandidate {index + 1} trial: {score}/{trial['n']} solved. "
                    "Consider a different general strategy for the next candidate."
                )
        if score > best_score:
            best = (files, note)
            best_score = score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
