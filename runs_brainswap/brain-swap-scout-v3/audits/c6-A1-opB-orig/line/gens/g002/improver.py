"""Improve both components using trial feedback and candidate selection."""

import re

SYSTEM = (
    "You improve an AI agent whose solver writes Python functions from examples. "
    "Optimize generalization rather than fitting the development task IDs."
)
BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'
CANDIDATES = 2
TRIAL_TASKS = 8


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
            for ex in item["examples"][:3]:
                lines.append(f"    f({ex['input']}) == {ex['output']}")
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
        "Rewrite BOTH files, preserving their contracts. Improve generalization "
        "on hidden tests, not just the displayed examples. Consider ambiguity, "
        "edge cases, budget limits, and checking shown examples. The new "
        "improver.py must differ from the current one and help future rounds. "
        "Return each complete source between lines <file name=\"NAME\"> and "
        "</file>, then <note>one line for the next generation</note>."
    )
    best = None
    top = -1
    feedback = ""
    for _ in range(CANDIDATES):
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if (
            "solver.py" not in files
            or "improver.py" not in files
            or files["improver.py"] == procedure
            or "def f" not in files["solver.py"]
        ):
            feedback = "\nThe previous proposal was incomplete. Return both full files."
            continue
        try:
            result = api.trial(files["solver.py"], TRIAL_TASKS)
            score = result["solved"]
        except api.BudgetExceeded:
            if best is None:
                best = (files, note)
            break
        if score > top:
            best, top = (files, note), score
        feedback = (
            f"\nThe previous candidate solved {score} trial tasks. "
            "Propose a distinct improvement addressing likely hidden-test failures."
        )
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
