"""Generate and trial competing solver improvements."""

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
                lines.append(
                    "    f(%r) == %r" % (example["input"], example["output"])
                )
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    improver = api.source("improver.py")
    solved = sum(bool(item["passed"]) for item in ctx["results"])
    prompt = (
        "Generation %s: solved %s of %s development tasks.\n\n"
        "=== FILE solver.py ===\n%s\n=== END FILE ===\n\n"
        "=== FILE improver.py ===\n%s\n=== END FILE ===\n\n"
        "Results:\n%s\n\nMemory:\n%s\n\n"
        "Rewrite BOTH files to improve generalization to hidden tests. "
        "Analyze failed examples and competing rules, including operation order "
        "and edge cases, without hardcoding task IDs or example answers. "
        "Use solver calls and checks economically. The improver must change "
        "and should use available trials to compare proposals. Preserve both "
        "contracts and standard-library restrictions. Reply with complete source "
        'for each file using a line <file name="NAME">, then source, then a line '
        "</file>. Finish with <note>one line for the next generation</note>."
        % (
            ctx["generation"], solved, len(ctx["results"]), solver, improver,
            describe(ctx["results"]), ctx["memory"] or "(none)",
        )
    )
    best = None
    best_score = -1
    feedback = ""
    for attempt in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            response = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(response)
        if "solver.py" not in files or "improver.py" not in files:
            feedback += "\nA previous proposal omitted a required file."
            continue
        if files["improver.py"] == improver:
            feedback += "\nA previous proposal did not change improver.py."
            continue
        try:
            compile(files["solver.py"], "solver.py", "exec")
            compile(files["improver.py"], "improver.py", "exec")
        except (SyntaxError, ValueError, TypeError):
            feedback += "\nA previous proposal contained invalid Python."
            continue

        score = -1
        try:
            remaining = api.budget().get("trial_tasks", 0)
            if remaining and ctx["results"]:
                # Reserve a comparable trial for another proposal when possible.
                count = min(len(ctx["results"]), max(1, remaining // 2))
                if attempt == 2:
                    count = min(len(ctx["results"]), remaining)
                trial = api.trial(files["solver.py"], count)
                score = trial["solved"] / max(1, trial["n"])
                feedback += "\nPrevious candidate trial: %s of %s solved." % (
                    trial["solved"], trial["n"]
                )
        except api.BudgetExceeded:
            pass
        if best is None or score > best_score:
            best = (files, note)
            best_score = score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
