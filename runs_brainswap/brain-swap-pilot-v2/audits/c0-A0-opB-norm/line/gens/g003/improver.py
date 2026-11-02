"""Improve the solver and retain an adaptable improvement procedure."""

import re

SYSTEM = (
    "You improve an AI agent that writes Python functions from input/output examples. "
    "Respect both contracts and the standard-library-only policy."
)
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
            lines.append("- %s: solved" % result["id"])
        else:
            lines.append("- %s: FAILED (%s)" % (result["id"], result["failure"]))
            for example in result["examples"]:
                lines.append("    f(%r) == %r" % (example["input"], example["output"]))
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    improver = api.source("improver.py")
    solved = sum(result["passed"] for result in ctx["results"])
    prompt = (
        "Generation %s: solved %s of %s development tasks.\n\n"
        "=== solver.py ===\n%s\n=== END ===\n\n"
        "=== improver.py ===\n%s\n=== END ===\n\n"
        "Results:\n%s\n\nMemory:\n%s\n\n"
        "Rewrite BOTH files while preserving their contracts. Improve generalization "
        "rather than hardcoding task IDs or examples. Use feedback from failures. "
        "The improver must change for the rewrite to be eligible. Keep code valid "
        "Python and use only permitted APIs and the standard library. Output each "
        "full source between standalone lines <file name=\"NAME\"> and </file>, "
        "then <note>one line</note>."
        % (ctx["generation"], solved, len(ctx["results"]), solver, improver,
           describe(ctx["results"]), ctx["memory"] or "(none)")
    )
    best = None
    best_score = -1
    feedback = ""
    for _ in range(3):
        budget = api.budget()
        if budget.get("llm_calls", 0) <= 0:
            break
        try:
            text = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(text)
        if "solver.py" not in files or "improver.py" not in files:
            feedback = "\nPrevious response omitted a required complete file."
            continue
        if files["improver.py"] == improver:
            feedback = "\nPrevious response did not change improver.py."
            continue
        try:
            compile(files["solver.py"], "solver.py", "exec")
            compile(files["improver.py"], "improver.py", "exec")
        except (SyntaxError, ValueError) as exc:
            feedback = "\nPrevious proposal had a syntax error: %s" % exc
            continue
        score = 0
        budget = api.budget()
        remaining = budget.get("trial_tasks", 0)
        if remaining:
            n = min(len(ctx["results"]), remaining)
            try:
                trial = api.trial(files["solver.py"], n)
                score = trial["solved"]
                feedback = "\nPrevious candidate trial: %s of %s solved. Propose a different improvement." % (
                    score, trial["n"]
                )
            except api.BudgetExceeded:
                pass
        if score > best_score:
            best = (files, note)
            best_score = score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
