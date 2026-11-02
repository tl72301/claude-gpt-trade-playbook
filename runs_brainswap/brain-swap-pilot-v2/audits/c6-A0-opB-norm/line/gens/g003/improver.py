"""Generate and, when possible, compare solver improvements."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver (writes Python functions from "
    "examples) and an improvement procedure (this program, which rewrites the agent)."
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
    for result in results:
        if result["passed"]:
            lines.append(f"- {result['id']}: solved")
        else:
            lines.append(f"- {result['id']}: FAILED ({result['failure']})")
            for example in result["examples"]:
                lines.append(f"    f({example['input']}) == {example['output']}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    improver = api.source("improver.py")
    solved = sum(result["passed"] for result in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}. The solver solved {solved} of "
        f"{len(ctx['results'])} development tasks.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{improver}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "Analyze the failed examples for generalizable ambiguity and hidden-test "
        "failure modes. Improve rule inference rather than hard-coding task IDs. "
        "Keep the API contracts and budget limits in mind. Rewrite BOTH files; "
        "improver.py must change too. For each file reply with a line "
        '<file name="NAME">, its full source, and a line </file>. '
        "Finish with <note>one line for the next generation</note>."
    )
    best = None
    best_score = -1
    for index in range(CANDIDATES):
        request = prompt
        if index:
            request += (
                "\nPropose a distinct strategy from the previous candidate, "
                "especially for ambiguous rules and hidden edge cases."
            )
        try:
            response = api.llm(request, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(response)
        if "solver.py" not in files or "improver.py" not in files:
            continue
        if best is None:
            best = (files, note)
        try:
            score = api.trial(files["solver.py"], TRIAL_TASKS)["solved"]
        except api.BudgetExceeded:
            break
        if score > best_score:
            best_score = score
            best = (files, note)
    if best is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": best[0], "note": best[1]}
