"""Propose and evaluate general-purpose solver improvements."""

import ast
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
                lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def usable(files):
    for name, entry in (("solver.py", "solve"), ("improver.py", "improve")):
        try:
            tree = ast.parse(files[name])
        except (KeyError, SyntaxError, ValueError, TypeError):
            return False
        if not any(isinstance(node, ast.FunctionDef) and node.name == entry
                   for node in tree.body):
            return False
    return True


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
        "competing hypotheses, derived outputs, ordering, boundary cases, check "
        "feedback, and budget exhaustion. Do not hardcode task IDs or examples. "
        "Improve the improvement procedure too. Return each complete source "
        "between lines <file name=\"NAME\"> and </file>, followed by "
        "<note>one line</note>."
    )

    best = None
    best_score = -1.0
    history = []
    initial = api.budget()
    calls = initial.get("llm_calls", 0)
    trials = initial.get("trial_tasks", 0)
    proposals = min(3, calls)
    trial_size = min(len(results), trials // proposals) if proposals else 0

    for index in range(proposals):
        if api.budget().get("llm_calls", 0) <= 0:
            break
        query = prompt
        if history:
            query += (
                "\nPrevious proposal trial results:\n" + "\n".join(history)
                + "\nPropose a materially different general improvement. "
                "Do not overfit the trial results."
            )
        try:
            reply = api.llm(query, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not usable(files):
            history.append(f"Proposal {index + 1}: missing or invalid source.")
            continue

        score = -1.0
        if trial_size and api.budget().get("trial_tasks", 0) >= trial_size:
            try:
                result = api.trial(files["solver.py"], trial_size)
                n = result.get("n", 0)
                if n:
                    score = result.get("solved", 0) / n
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
