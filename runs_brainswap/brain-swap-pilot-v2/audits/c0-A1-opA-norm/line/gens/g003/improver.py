"""Improvement procedure, revised in generation 1.

Changes: keeps a running memory of which results changed between generations,
asks for a diagnosis before rewriting, and carries lessons forward in NOTES.
"""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver (writes Python functions from "
    "examples) and an improvement procedure (this program, which rewrites the agent)."
)
CANDIDATES = 1
TRIAL_TASKS = 0
NOTES = [
    "Solver uses api.check feedback over several attempts; keep that loop.",
    "Failures with 'no function f' mean the reply lacked a def f block; enforce the format.",
    "Improver edits should be concrete: change one mechanism per generation and say why.",
]


BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    # Tags must sit on their own lines: this file's own source contains them mid-line.
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    rest = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    m = re.search(r"<note>(.*?)</note>", rest, re.DOTALL)
    return files, (m.group(1).strip() if m else "")


def describe(results):
    out = []
    for r in results:
        if r["passed"]:
            out.append(f"- {r['id']}: solved")
            continue
        out.append(f"- {r['id']}: FAILED ({r['failure']})")
        for ex in r["examples"][:3]:
            out.append(f"    f({ex['input']}) == {ex['output']}")
    return "\n".join(out)


def improve(ctx, api):
    solver_src = api.source("solver.py")
    improver_src = api.source("improver.py")
    solved = sum(r["passed"] for r in ctx["results"])
    total = len(ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}. The solver solved {solved} of {total} "
        f"development tasks.\n\n"
        f"=== FILE solver.py ===\n{solver_src}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{improver_src}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        "Strategy notes:\n"
        + "".join(f"- {n}\n" for n in NOTES)
        + f"\nMemory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "First, in a few sentences, diagnose the most common failure pattern. "
        "Then rewrite BOTH files. solver.py must solve more tasks. improver.py must "
        "also change, with one concrete mechanism you expect to speed future rounds "
        "(for example better memory, better feedback to the solver, or a trial step). "
        "A proposal that leaves improver.py unchanged is discarded. Keep both contracts. "
        "For each file, reply with a line <file name=\"NAME\">, then the full source, "
        "then a line </file>. Finish with <note>one line summarising the lesson for "
        "your next generation</note>."
    )
    best, best_score = None, -1
    for _ in range(CANDIDATES):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not files:
            continue
        score = 0
        if TRIAL_TASKS and "solver.py" in files:
            score = api.trial(files["solver.py"], TRIAL_TASKS)["solved"]
        if score > best_score:
            best, best_score = (files, note), score
    if best is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": best[0], "note": best[1]}
