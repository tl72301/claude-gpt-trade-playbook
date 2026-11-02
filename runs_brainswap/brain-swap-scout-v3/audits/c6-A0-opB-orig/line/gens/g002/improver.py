"""Improve the solver and the improvement procedure using development feedback."""

import re

SYSTEM = (
    "You improve an AI agent. Its solver writes Python functions from examples, "
    "and its improvement procedure rewrites both programs."
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
    solved = sum(bool(item["passed"]) for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: solved {solved} of "
        f"{len(ctx['results'])} development tasks.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files, preserving their contracts. The solver must generalize "
        "to hidden tests, not memorize development tasks. Checks cover only shown "
        "examples. Diagnose failures and consider competing interpretations and "
        "boundary cases. The improver must change as well and should use available "
        "trial budget to compare proposals. Return each full source between a line "
        '<file name="NAME"> and a line </file>, followed by '
        "<note>one line for the next generation</note>."
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
        if not files.get("solver.py") or not files.get("improver.py"):
            feedback = "\nThe previous proposal was missing a required complete file."
            continue
        if files["improver.py"] == procedure:
            feedback = "\nThe improver must also be changed."
            continue
        score = 0
        budget = api.budget()
        remaining = budget.get("trial_tasks", 0)
        if remaining:
            # Reserve trial capacity for later proposals when possible.
            n = min(len(ctx["results"]), max(1, remaining // max(1, 3 - index)))
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"] / max(1, result["n"])
                feedback = (
                    f"\nThe preceding proposal solved {result['solved']} of "
                    f"{result['n']} trial tasks. Propose a different improvement."
                )
            except api.BudgetExceeded:
                pass
        if score > best_score:
            best, best_score = (files, note), score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
