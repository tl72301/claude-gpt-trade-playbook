"""Improvement procedure, revised in generation 2.

Changes: failures are grouped by type to guide the rewrite, and when trial
budget is available several candidate rewrites are scored on development tasks
and the best one is kept.
"""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver (writes Python functions from "
    "examples) and an improvement procedure (this program, which rewrites the agent)."
)
CANDIDATES = 2
TRIAL_TASKS = 4
NOTES = [
    "Keep solver changes that use checker feedback across attempts.",
    "Make improver changes that alter how candidates are chosen or diagnosed.",
]


BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    # Tags must sit on their own lines: this file's own source contains them mid-line.
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    rest = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    note = re.search(r"<note>(.*?)</note>", rest, re.DOTALL)
    return files, (note.group(1).strip() if note else "")


def describe(results):
    lines = []
    for item in results:
        if item["passed"]:
            lines.append(f"- {item['id']}: solved")
            continue
        lines.append(f"- {item['id']}: FAILED ({item['failure']})")
        for ex in item["examples"][:3]:
            lines.append(f"    f({ex['input']}) == {ex['output']}")
    return "\n".join(lines)


def diagnose(results):
    failed = [r for r in results if not r["passed"]]
    if not failed:
        return "All development tasks solved; preserve behaviour and generalisation."
    near = [r["id"] for r in failed if "/" in str(r["failure"]) and
            _ratio(r["failure"]) >= 0.5]
    far = [r["id"] for r in failed if r["id"] not in near]
    return (
        f"{len(failed)} failing tasks. Near misses (over half of hidden tests pass): "
        f"{near or 'none'}. Far misses: {far or 'none'}. Prioritise the far misses "
        "with a general rule rather than patches."
    )


def _ratio(failure):
    match = re.search(r"(\d+)/(\d+)", str(failure))
    if not match or int(match.group(2)) == 0:
        return 0.0
    return int(match.group(1)) / int(match.group(2))


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}. The solver solved {solved} of "
        f"{len(ctx['results'])} development tasks.\n"
        f"Diagnosis: {diagnose(ctx['results'])}\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        "Strategy notes:\n" + "".join(f"- {note}\n" for note in NOTES)
        + f"\nMemory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files. solver.py must solve more tasks. improver.py (this "
        "program) must also change in a way you expect to make future rounds improve "
        "the solver faster: a proposal that leaves improver.py unchanged is discarded. "
        "Keep both contracts. For each file, reply with a line "
        '<file name="NAME">, then the full source, then a line </file>. '
        "Finish with <note>one line for your next generation</note>."
    )
    best, top = None, -1
    for index in range(CANDIDATES):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not files:
            continue
        score = 0
        if TRIAL_TASKS and "solver.py" in files:
            try:
                score = api.trial(files["solver.py"], TRIAL_TASKS)["solved"]
            except api.BudgetExceeded:
                score = 0
        if score > top:
            best, top = (files, note), score
    if best is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": best[0], "note": best[1]}
