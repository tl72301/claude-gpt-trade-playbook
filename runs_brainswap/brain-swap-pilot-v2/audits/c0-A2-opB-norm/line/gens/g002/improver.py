"""Generate and, when possible, trial competing solver improvements."""

import re

SYSTEM = (
    "You improve an AI agent that writes Python functions from examples. "
    "Preserve the documented API contracts and standard-library restrictions."
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
    solved = sum(bool(r["passed"]) for r in ctx["results"])
    prompt = (
        "Generation %s: solved %s of %s development tasks.\n\n"
        "=== FILE solver.py ===\n%s\n=== END FILE ===\n\n"
        "=== FILE improver.py ===\n%s\n=== END FILE ===\n\n"
        "Results:\n%s\n\nMemory:\n%s\n\n"
        "Rewrite BOTH files to improve generalization to hidden tests. "
        "Analyze the failed examples for plausible underlying rules and "
        "ambiguities, but do not hardcode task IDs or example answers. "
        "Make economical use of solver LLM calls and checks. The improver must "
        "also change and should use available trials to compare proposals. "
        "Preserve both contracts. Reply with complete source for each file, "
        "using a line <file name=\"NAME\">, then source, then a line </file>. "
        "Finish with <note>one line for the next generation</note>."
        % (ctx["generation"], solved, len(ctx["results"]), solver, improver,
           describe(ctx["results"]), ctx["memory"] or "(none)")
    )
    best = None
    best_score = -1
    feedback = ""
    # Leave room for multiple candidates when the improvement budget allows.
    for _ in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            text = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(text)
        if "solver.py" not in files or "improver.py" not in files:
            feedback += "\nPrevious proposal omitted a required complete file."
            continue
        if files["improver.py"] == improver:
            feedback += "\nPrevious proposal did not change improver.py."
            continue
        score = 0
        try:
            remaining = api.budget().get("trial_tasks", 0)
            if remaining:
                n = min(remaining, len(ctx["results"]))
                trial = api.trial(files["solver.py"], n)
                score = trial["solved"] / max(1, trial["n"])
                feedback += "\nPrevious candidate trial: %s of %s solved." % (
                    trial["solved"], trial["n"])
        except api.BudgetExceeded:
            pass
        if score > best_score:
            best = (files, note)
            best_score = score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
