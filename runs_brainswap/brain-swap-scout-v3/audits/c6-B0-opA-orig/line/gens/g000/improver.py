"""Generate and compare budget-aware solver improvements."""

import re


SYSTEM = (
    "You improve an AI agent that writes Python functions from input/output "
    "examples. Preserve the stated interfaces and standard-library restrictions."
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
        status = "solved" if item["passed"] else "FAILED (" + str(item["failure"]) + ")"
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
        f"Generation {ctx['generation']}. The solver solved {solved} of "
        f"{len(ctx['results'])} development tasks.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files. Improve generalization to hidden tests, not just "
        "shown examples. Analyze failure patterns and avoid memorizing task IDs "
        "or examples. The solver must retain solve(task, api) -> source. "
        "The improver must retain improve(ctx, api) and must change, or the "
        "rewrite is discarded. Respect API budgets and contracts. "
        "Return complete source for each file using lines "
        '<file name="solver.py"> and <file name="improver.py">, '
        "each closed by a line </file>. Finish with <note>one line</note>."
    )
    budget = api.budget()
    calls = min(3, budget.get("llm_calls", 0))
    trial_n = min(
        len(ctx["results"]),
        budget.get("trial_tasks", 0) // max(1, calls),
    )
    directions = [
        "Focus on independent hypothesis generation and reliable comparison of general rules.",
        "Explore systematic composition of filtering, mapping, counting and sequence operations.",
        "Focus on ambiguous examples, hidden edge cases, and avoiding premature selection of passing candidates.",
    ]
    best = None
    best_score = -1
    history = []
    for index in range(calls):
        prompt = base + "\n\nDirection: " + directions[index]
        if history:
            prompt += "\nEarlier candidate trial scores: " + "; ".join(history)
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            continue
        if files["improver.py"].strip() == procedure.strip():
            continue
        try:
            compile(files["solver.py"], "solver.py", "exec")
            compile(files["improver.py"], "improver.py", "exec")
        except (SyntaxError, ValueError, TypeError):
            continue
        score = 0
        if trial_n and api.budget().get("trial_tasks", 0) >= trial_n:
            try:
                trial = api.trial(files["solver.py"], trial_n)
                score = trial["solved"]
                history.append(
                    f"candidate {index + 1}: {score}/{trial.get('n', trial_n)}"
                )
            except api.BudgetExceeded:
                pass
        if best is None or score > best_score:
            best = (files, note)
            best_score = score
    if best is None:
        return {"files": {}, "note": "No usable proposal generated."}
    return {"files": best[0], "note": best[1]}
