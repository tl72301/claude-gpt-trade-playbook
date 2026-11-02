"""Improvement procedure, revised in generation 1.

Changes: the prompt carries full failure detail and the lessons so far; two candidate
rewrites are generated; each candidate is trialled on a few development tasks when the
budget allows; a failed trial is scored as zero rather than crashing the procedure.
"""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver (writes Python functions from "
    "examples) and an improvement procedure (this program, which rewrites the agent)."
)
CANDIDATES = 2
TRIAL_TASKS = 3
NOTES = [
    "Solver: self-check against shown examples and retry with the failing case and previous code.",
    "Procedure: generate candidates, trial them, and keep the best; record lessons in the note.",
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
        for ex in item["examples"][:5]:
            lines.append(f"    f({ex['input']}) == {ex['output']}")
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
        f"Results (failed tasks show examples the solver got wrong or could not infer):\n"
        f"{describe(ctx['results'])}\n\n"
        "Strategy notes:\n" + "".join(f"- {note}\n" for note in NOTES)
        + f"\nMemory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files. solver.py must solve more tasks; keep it general, not "
        "example-specific. improver.py must change in a way that makes future rounds "
        "improve the solver faster (for example, better failure feedback, more useful "
        "candidates, or memory of which changes helped). A proposal that leaves "
        "improver.py unchanged is discarded. Keep both contracts. For each file, reply "
        'with a line <file name="NAME">, then the full source, then a line </file>. '
        "Finish with <note>one line of lessons for your next generation</note>."
    )
    best, top = None, -1
    for _ in range(CANDIDATES):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not files or "solver.py" not in files:
            continue
        score = 0
        if TRIAL_TASKS:
            try:
                score = api.trial(files["solver.py"], TRIAL_TASKS)["solved"]
            except api.BudgetExceeded:
                score = 0
            except Exception:
                score = 0
        if score > top:
            best, top = (files, note), score
    if best is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": best[0], "note": best[1]}
