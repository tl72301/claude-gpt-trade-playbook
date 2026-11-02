"""Improve the solver using development feedback and optional trials."""
import re

SYSTEM = (
    "You improve an AI agent that writes Python functions from examples. "
    "Propose generalizable improvements, not task-ID-specific memorization."
)
BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'

def parse(text):
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    rest = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    note = re.search(r"<note>(.*?)</note>", rest, re.DOTALL)
    return files, note.group(1).strip() if note else ""

def describe(results):
    lines = []
    for item in results:
        lines.append("- %s: %s" % (
            item["id"], "solved" if item["passed"] else
            "FAILED (%s)" % item["failure"]))
        if not item["passed"]:
            for ex in item["examples"]:
                lines.append("    f(%r) == %r" % (ex["input"], ex["output"]))
    return "\n".join(lines)

def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(bool(item["passed"]) for item in ctx["results"])
    prompt = (
        "Generation %s: solved %s/%s development tasks.\n\n"
        "=== solver.py ===\n%s\n=== improver.py ===\n%s\n"
        "=== results ===\n%s\n\nMemory: %s\n\n"
        "Rewrite BOTH files, preserving their contracts. Improve generalization "
        "from examples, including accurate output ordering and avoiding overly "
        "specific rules. Do not hard-code task IDs or example outputs. Use the "
        "available budgets prudently. The improver must change too. Return each "
        "full source between lines <file name=\"solver.py\"> or "
        "<file name=\"improver.py\"> and </file>, then <note>...</note>."
        % (ctx["generation"], solved, len(ctx["results"]), solver, procedure,
           describe(ctx["results"]), ctx["memory"] or "(none)")
    )
    best = None
    best_score = -1
    feedback = ""
    for _ in range(3):
        if api.budget().get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            feedback = "\nThe previous proposal did not contain both complete files."
            continue
        score = 0
        remaining = api.budget().get("trial_tasks", 0)
        if remaining:
            n = min(remaining, len(ctx["results"]))
            try:
                trial = api.trial(files["solver.py"], n)
                score = trial["solved"] / max(1, trial["n"])
                feedback = (
                    "\nThe previous proposal scored %s/%s in a trial. "
                    "Seek a different, more reliable approach." %
                    (trial["solved"], trial["n"])
                )
            except api.BudgetExceeded:
                pass
        if best is None or score > best_score:
            best, best_score = (files, note), score
        if remaining <= len(ctx["results"]):
            break
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
