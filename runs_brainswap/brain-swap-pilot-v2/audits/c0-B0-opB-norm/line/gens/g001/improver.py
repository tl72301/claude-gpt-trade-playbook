"""Propose and trial multiple solver improvements, retaining the best candidate."""
import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver (writes Python functions from "
    "examples) and an improvement procedure (this program, which rewrites the agent)."
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
        lines.append(
            "- %s: %s" % (
                result["id"],
                "solved" if result["passed"] else "FAILED (%s)" % result["failure"],
            )
        )
        if not result["passed"]:
            for example in result["examples"]:
                lines.append("    f(%r) == %r" % (example["input"], example["output"]))
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    improver = api.source("improver.py")
    solved = sum(r["passed"] for r in ctx["results"])
    prompt = (
        "Generation %s: %s of %s tasks solved.\n\n"
        "=== FILE solver.py ===\n%s\n=== END FILE ===\n\n"
        "=== FILE improver.py ===\n%s\n=== END FILE ===\n\n"
        "Results:\n%s\n\nMemory: %s\n\n"
        "Rewrite BOTH files, preserving their contracts. Improve generalization to "
        "hidden inputs, not just shown examples. Consider ambiguity in rules, edge "
        "cases, budget constraints, and checks. Do not hardcode development task IDs "
        "or example answers. The improver must change too; make future search more "
        "effective. Return each complete source between lines "
        '<file name="solver.py"> and </file>, or '
        '<file name="improver.py"> and </file>. '
        "Finish with <note>one line for the next generation</note>."
    ) % (
        ctx["generation"], solved, len(ctx["results"]), solver, improver,
        describe(ctx["results"]), ctx["memory"] or "(none)",
    )

    best = None
    best_score = -1
    feedback = []
    for i in range(3):
        budget = api.budget()
        if budget.get("llm_calls", 0) <= 0:
            break
        extra = ""
        if feedback:
            extra = "\nPrior trial results: " + "; ".join(feedback)
            extra += "\nPropose a meaningfully different improvement."
        try:
            text = api.llm(prompt + extra, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(text)
        if "solver.py" not in files or "improver.py" not in files:
            continue
        if files["improver.py"] == improver:
            continue
        remaining = api.budget().get("trial_tasks", 0)
        n = min(len(ctx["results"]), remaining)
        score = 0
        if n:
            try:
                trial = api.trial(files["solver.py"], n)
                score = trial["solved"] / max(1, trial["n"])
                feedback.append("candidate %d: %s/%s" % (i + 1, trial["solved"], trial["n"]))
            except api.BudgetExceeded:
                pass
        if score > best_score:
            best, best_score = (files, note), score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
