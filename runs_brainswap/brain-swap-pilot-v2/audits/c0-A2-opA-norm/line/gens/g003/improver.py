"""Improver v2: diagnoses all failures, keeps a persistent lesson list, and
uses trial-based selection between candidate rewrites when budget allows."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver (writes Python functions from "
    "examples) and an improvement procedure (this program, which rewrites the agent)."
)
CANDIDATES = 2
TRIAL_TASKS = 4
NOTES = []


BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    # Tags must sit on their own lines: this file's own source contains them mid-line.
    v0 = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    v1 = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    v2 = re.search(r"<note>(.*?)</note>", v1, re.DOTALL)
    return v0, (v2.group(1).strip() if v2 else "")


def describe(results):
    out = []
    for r in results:
        if r["passed"]:
            out.append(f"- {r['id']}: solved")
            continue
        out.append(f"- {r['id']}: FAILED ({r['failure']})")
        for ex in r["examples"][:5]:
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
        "Lessons kept so far:\n"
        + "".join(f"- {n}\n" for n in NOTES)
        + f"\nMemory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "Before rewriting, briefly diagnose why the failing tasks fail (is the solver "
        "guessing rules without verifying them? does it ignore edge cases?). "
        "Rewrite BOTH files. solver.py must solve more tasks. improver.py must change "
        "in a concrete way that should make future generations improve faster "
        "(for example: better diagnosis, better feedback to the solver, or keeping "
        "useful lessons in the notes). A proposal that leaves improver.py unchanged is "
        "discarded. Keep both contracts. For each file, reply with a line "
        '<file name="NAME">, then the full source, then a line </file>. '
        "Finish with <note>one line: the key lesson plus your next priority</note>."
    )
    best, best_score = None, -1
    for _ in range(CANDIDATES):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not files or "improver.py" not in files:
            continue
        score = 0
        if TRIAL_TASKS and "solver.py" in files:
            try:
                score = api.trial(files["solver.py"], TRIAL_TASKS)["solved"]
            except api.BudgetExceeded:
                score = 0
        if score > best_score:
            best, best_score = (files, note), score
    if best is None:
        return {"files": {}, "note": "no usable proposal"}
    if best_score >= 0 and note_text(best[1]):
        NOTES.append(note_text(best[1]))
    return {"files": best[0], "note": best[1]}


def note_text(note):
    return note.strip()[:200]
