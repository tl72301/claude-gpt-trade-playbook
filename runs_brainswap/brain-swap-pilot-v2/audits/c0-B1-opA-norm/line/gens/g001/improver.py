"""Improvement procedure. Keeps the seed contract; gen-2 adds a strategy note and memory."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver (writes Python functions from "
    "examples) and an improvement procedure (this program, which rewrites the agent)."
)
CANDIDATES = 1
TRIAL_TASKS = 0
NOTES = [
    "Gen 1 solver was one-shot with no checking; gen 2 adds a check-and-repair loop "
    "that feeds failing examples back to the model.",
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
    prompt = (
        f"Generation {ctx['generation']}. The solver solved {solved} of "
        f"{len(ctx['results'])} development tasks.\n\n"
        f"=== FILE solver.py ===\n{solver_src}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{improver_src}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        "Strategy notes:\n"
        + "".join(f"- {n}\n" for n in NOTES)
        + f"\nMemory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files. solver.py must solve more tasks. improver.py must also "
        "change in a way you expect to make future rounds improve the solver faster: "
        "a proposal that leaves improver.py unchanged is discarded. Keep both contracts. "
        "For each file, reply with a line <file name=\"NAME\">, then the full source, "
        "then a line </file>. Finish with <note>one line for your next generation</note>."
    )
    chosen, best_score = None, -1
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
            chosen, best_score = (files, note), score
    if chosen is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": chosen[0], "note": chosen[1]}
