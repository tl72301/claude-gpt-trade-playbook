"""Generate and, where budget permits, compare improvements to the agent."""

import re

SYSTEM = (
    "You improve an AI agent. Its solver writes Python functions from examples, "
    "and its improvement procedure rewrites both components. Preserve contracts."
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
        f"Generation {ctx['generation']}: {solved}/{len(ctx['results'])} solved.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Improve generalization to hidden inputs, not just shown examples. Analyze "
        "failure patterns and resource limits. Keep the solve and improve contracts. "
        "Rewrite BOTH files: acceptance requires a changed improver.py and a solver "
        "that solves strictly more development tasks. For each file output a line "
        '<file name="NAME">, its complete source, and a line </file>. '
        "Finish with <note>one line for the next generation</note>."
    )
    best = None
    best_score = -1
    budget = api.budget()
    calls = min(2, budget.get("llm_calls", 0))
    trial_budget = budget.get("trial_tasks", 0)
    n = min(len(ctx["results"]), trial_budget // calls) if calls else 0

    for index in range(calls):
        request = prompt
        if index:
            request += (
                "\nPropose a materially different strategy from the previous "
                "candidate, while preserving any useful current behavior."
            )
        try:
            reply = api.llm(request, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            continue
        if files["improver.py"] == procedure:
            continue
        score = 0
        if n:
            try:
                score = api.trial(files["solver.py"], n)["solved"]
            except api.BudgetExceeded:
                break
        if score > best_score:
            best, best_score = (files, note), score

    if best is None:
        return {"files": {}, "note": "No usable proposal generated."}
    return {"files": best[0], "note": best[1]}
