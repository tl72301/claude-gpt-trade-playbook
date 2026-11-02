"""Improvement procedure, revised: failure categories, candidate selection, and a validity gate."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver (writes Python functions from "
    "examples) and an improvement procedure (this program, which rewrites the agent)."
)
CANDIDATES = 2
TRIAL_TASKS = 0
NOTES = [
    "Gen 2: the solver extracts code robustly and repairs up to 3 times using check feedback "
    "on all failing shown examples. Remaining failures are mostly wrong rules on length, sign, "
    "and index-dependent patterns.",
]


BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    # Tags must sit on their own lines: this file's own source contains them mid-line.
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    rest = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    m = re.search(r"<note>(.*?)</note>", rest, re.DOTALL)
    return files, (m.group(1).strip() if m else "")


def valid(files):
    # Validity gate: a proposal must keep both contracts or it is discarded.
    if "solver.py" in files:
        s = files["solver.py"]
        if "def solve(" not in s or "BudgetExceeded" not in s:
            return False
    if "improver.py" in files:
        if "def improve(" not in files["improver.py"]:
            return False
    return bool(files)


def describe(results):
    lines = []
    for r in results:
        if r["passed"]:
            lines.append(f"- {r['id']}: solved")
            continue
        lines.append(f"- {r['id']}: FAILED ({r['failure']})")
        for ex in r["examples"][:4]:
            lines.append(f"    f({ex['input']}) == {ex['output']}")
    return "\n".join(lines)


def categorize(results):
    failed = [r for r in results if not r["passed"]]
    solved = len(results) - len(failed)
    worst = sorted(failed, key=lambda r: float(str(r["failure"]).split("/")[0] or 0))[:3]
    worst_ids = ", ".join(r["id"] for r in worst) or "none"
    return (
        f"Solved {solved}/{len(results)}. Weakest tasks by hidden-test score: {worst_ids}. "
        "Prioritise changes that fix whole failure classes, not single tasks."
    )


def improve(ctx, api):
    solver_src = api.source("solver.py")
    improver_src = api.source("improver.py")
    solved = sum(r["passed"] for r in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}. The solver solved {solved} of "
        f"{len(ctx['results'])} development tasks.\n"
        f"{categorize(ctx['results'])}\n\n"
        f"=== FILE solver.py ===\n{solver_src}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{improver_src}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        "Strategy notes:\n"
        + "".join(f"- {n}\n" for n in NOTES)
        + f"\nMemory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files. solver.py must solve more tasks. improver.py must also change "
        "so future rounds improve the solver faster (for example, better failure reports or "
        "candidate selection). A proposal that leaves improver.py unchanged is discarded. "
        "Keep both contracts. For each file, reply with a line <file name=\"NAME\">, then the "
        "full source, then a line </file>. Finish with <note>one line for your next generation, "
        "including the solved count</note>."
    )
    best, best_score = None, -1
    for _ in range(CANDIDATES):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not valid(files):
            continue
        score = 0
        if TRIAL_TASKS and "solver.py" in files:
            score = api.trial(files["solver.py"], TRIAL_TASKS)["solved"]
        if score > best_score:
            best, best_score = (files, note), score
    if best is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": best[0], "note": best[1]}
