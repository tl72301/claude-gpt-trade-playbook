"""Iterative improvement procedure with budget-aware proposal trials."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver that writes Python "
    "functions from examples and an improvement procedure that rewrites the agent."
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
                lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: solved {solved}/{len(ctx['results'])}.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Earlier memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files, keeping their contracts. Improve generalization on "
        "unseen inputs, not just the shown examples. Avoid task-ID-specific "
        "solutions. Consider ambiguity between plausible rules, edge cases, "
        "and using available checks and LLM budget effectively. The improver "
        "must also change and should help later generations. Return full source "
        "for each file between standalone lines <file name=\"NAME\"> and "
        "</file>, then <note>one line for the next generation</note>."
    )
    budget = api.budget()
    trial_budget = budget.get("trial_tasks", 0)
    n = min(len(ctx["results"]), trial_budget)
    best = None
    best_score = -1
    feedback = ""
    for _ in range(3):
        if api.budget().get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not files.get("solver.py") or not files.get("improver.py"):
            feedback += "\nThe last proposal omitted a required complete file."
            continue
        score = 0
        if n and api.budget().get("trial_tasks", 0) >= n:
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"]
                feedback += (
                    f"\nA previous proposal solved {score}/{n} trial tasks. "
                    "Seek a stronger general approach."
                )
            except api.BudgetExceeded:
                n = 0
        elif best is not None:
            break
        if score > best_score:
            best = (files, note)
            best_score = score
        if n == 0:
            break
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
