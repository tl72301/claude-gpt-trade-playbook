"""Improve the solver using development failures and optional comparative trials."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver that writes Python functions "
    "from examples, and an improvement procedure that rewrites the agent."
)
CANDIDATES = 2
TRIAL_TASKS = 16
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
            continue
        lines.append(f"- {item['id']}: FAILED ({item['failure']})")
        for ex in item["examples"]:
            lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}. The solver solved {solved} of "
        f"{len(ctx['results'])} development tasks.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "Diagnose generalizable failure modes, including ambiguous rules and boundary "
        "conditions. Do not hard-code task IDs or example inputs. Preserve successful "
        "behavior and respect API budgets. Rewrite BOTH files: solver.py to solve "
        "more tasks, and improver.py to improve future search. Keep both contracts. "
        "For each file, reply with a line "
        '<file name="NAME">, then the full source, then a line </file>. '
        "Finish with <note>one line for your next generation</note>."
    )
    best = None
    top = -1
    feedback = ""
    for index in range(CANDIDATES):
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not all(name in files for name in ("solver.py", "improver.py")):
            feedback = "\nThe previous proposal was missing a required file."
            continue
        score = 0
        try:
            result = api.trial(files["solver.py"], TRIAL_TASKS)
            score = result["solved"]
            feedback = (
                f"\nThe preceding candidate solved {score} trial tasks. "
                "Propose a distinct improvement, preserving what works."
            )
        except api.BudgetExceeded:
            if best is None:
                best = (files, note)
            break
        if score > top:
            best, top = (files, note), score
    if best is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": best[0], "note": best[1]}
