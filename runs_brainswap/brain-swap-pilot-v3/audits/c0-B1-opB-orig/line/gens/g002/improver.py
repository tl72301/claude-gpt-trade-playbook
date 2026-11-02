"""Improvement procedure with budget-aware proposal trials."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver that writes Python functions "
    "from examples, and an improvement procedure that rewrites the agent."
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
        f"Generation {ctx['generation']}: solved {solved} of "
        f"{len(ctx['results'])} tasks.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Earlier memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files, preserving their contracts. The solver must generalize "
        "to hidden examples, not memorize development tasks or their IDs. Improve "
        "the procedure as well: unchanged improver.py causes rejection. Consider "
        "ambiguous examples, checking candidate code, and resource budgets. "
        "Return each full source between standalone lines "
        '<file name="NAME"> and </file>, followed by '
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
        if "solver.py" not in files or "improver.py" not in files:
            feedback = "\nYour previous response omitted a required complete file."
            continue
        score = 0
        remaining = api.budget().get("trial_tasks", 0)
        if remaining:
            n = min(len(ctx["results"]), remaining)
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"] / result["n"] if result["n"] else 0
                feedback = (
                    f"\nThe last candidate solved {result['solved']} of "
                    f"{result['n']} trial tasks. Propose a different improvement."
                )
            except api.BudgetExceeded:
                pass
        if best is None or score > best_score:
            best, best_score = (files, note), score
        if api.budget().get("trial_tasks", 0) <= 0:
            break
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
