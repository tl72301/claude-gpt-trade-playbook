"""Propose and evaluate general-purpose solver improvements."""

import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from input/output "
    "examples. Design robust general-purpose improvements rather than hardcoding "
    "development task IDs or answers."
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
        status = "solved" if item["passed"] else f"FAILED ({item['failure']})"
        lines.append(f"- {item['id']}: {status}")
        if not item["passed"]:
            for ex in item["examples"]:
                lines.append(f"    f({ex['input']}) == {ex['output']}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    results = ctx["results"]
    solved = sum(item["passed"] for item in results)
    prompt = (
        f"Generation {ctx['generation']}: solved {solved}/{len(results)} tasks.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(results)}\n"
        f"Memory: {ctx['memory'] or '(none)'}\n\n"
        "Rewrite both files while preserving their contracts. Improve hidden-test "
        "generalization, not just agreement with shown examples. Consider "
        "ambiguity, edge cases, check feedback, and budget exhaustion. Do not "
        "hardcode task IDs or examples. Improve the improvement procedure too. "
        "Return each complete source between lines <file name=\"NAME\"> and "
        "</file>, followed by <note>one line</note>."
    )

    best = None
    best_score = -1.0
    history = []
    # Keep trials comparable: use the same number of tasks per proposal.
    initial = api.budget()
    trial_total = initial.get("trial_tasks", 0)
    calls = initial.get("llm_calls", 0)
    proposals = min(3, calls)
    trial_size = min(len(results), trial_total // proposals) if proposals else 0

    for index in range(proposals):
        if api.budget().get("llm_calls", 0) <= 0:
            break
        query = prompt
        if history:
            query += (
                "\nPrevious proposal trial results:\n" + "\n".join(history)
                + "\nPropose a materially different improvement addressing "
                "the weaknesses while retaining generality."
            )
        try:
            reply = api.llm(query, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            history.append(f"Proposal {index + 1}: missing a required file.")
            continue

        # An untested proposal is only a fallback, never preferred to a trial.
        score = -1.0
        if trial_size and api.budget().get("trial_tasks", 0) >= trial_size:
            try:
                result = api.trial(files["solver.py"], trial_size)
                n = result.get("n", 0)
                if n:
                    score = result["solved"] / n
                history.append(
                    f"Proposal {index + 1}: solved {result.get('solved', 0)}/"
                    f"{n} in trial. Note: {note}"
                )
            except api.BudgetExceeded:
                history.append(f"Proposal {index + 1}: trial budget exhausted.")
        else:
            history.append(f"Proposal {index + 1}: not trialled. Note: {note}")

        if best is None or score > best_score:
            best, best_score = (files, note), score

    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}

