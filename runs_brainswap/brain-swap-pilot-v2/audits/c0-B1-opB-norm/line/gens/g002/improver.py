"""Propose and optionally trial improvements to the solver and improver."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver that writes Python functions "
    "from examples and an improvement procedure that rewrites the agent."
)
BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    remainder = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    note = re.search(r"<note>(.*?)</note>", remainder, re.DOTALL)
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
    solved = sum(bool(r["passed"]) for r in ctx["results"])
    prompt = (
        "Generation %s. Current solver solved %s of %s development tasks.\n\n"
        "=== FILE solver.py ===\n%s\n=== END FILE ===\n\n"
        "=== FILE improver.py ===\n%s\n=== END FILE ===\n\n"
        "Results:\n%s\n\nMemory:\n%s\n\n"
        "Rewrite BOTH files, preserving their contracts and using only permitted "
        "standard-library operations. The solver should generalize beyond examples, "
        "use its budget carefully, and validate candidates when useful. The improver "
        "must change as well and should help future generations. Return each complete "
        "file between lines <file name=\"NAME\"> and </file>, followed by "
        "<note>one line</note>."
        % (ctx["generation"], solved, len(ctx["results"]), solver, improver,
           describe(ctx["results"]), ctx["memory"] or "(none)")
    )
    best = None
    best_score = -1
    feedback = ""
    for attempt in range(3):
        budget = api.budget()
        if budget.get("llm_calls", 0) <= 0:
            break
        try:
            text = api.llm(prompt + feedback, system=SYSTEM)
            files, note = parse(text)
            if not files.get("solver.py") or not files.get("improver.py"):
                feedback = "\nThe previous proposal omitted a required complete file."
                continue
            score = 0
            remaining = api.budget().get("trial_tasks", 0)
            if remaining:
                n = min(remaining, len(ctx["results"]))
                trial = api.trial(files["solver.py"], n)
                score = trial["solved"]
                feedback = "\nThe last candidate's trial solved %s of %s tasks. Propose a different improvement." % (
                    trial["solved"], trial["n"])
            if score > best_score:
                best, best_score = (files, note), score
            if not remaining:
                break
        except api.BudgetExceeded:
            break
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
