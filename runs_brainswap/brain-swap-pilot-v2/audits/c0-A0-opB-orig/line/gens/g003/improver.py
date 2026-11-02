"""Propose and, when possible, trial multiple solver improvements."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver that writes Python functions "
    "from examples and an improvement procedure that rewrites the agent."
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
        if item["passed"]:
            lines.append(f"- {item['id']}: solved")
        else:
            lines.append(f"- {item['id']}: FAILED ({item['failure']})")
            for ex in item["examples"]:
                lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: {solved}/{len(ctx['results'])} tasks solved.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Memory: {ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files, preserving their contracts. Improve generalization on "
        "hidden inputs rather than hardcoding development task IDs or examples. "
        "Consider ambiguity in inferred rules and avoid regressions. The improver "
        "must change too; make future search more effective. Return full sources "
        'inside <file name="solver.py"> and <file name="improver.py"> tags, '
        "each tag on its own line, followed by <note>one line</note>."
    )
    best = None
    best_score = -1
    feedback = ""
    for index in range(3):
        budget = api.budget()
        if not budget.get("llm_calls", 0):
            break
        try:
            reply = api.llm(
                prompt + feedback
                + (f"\nProposal {index + 1}: explore a distinct approach." if index else ""),
                system=SYSTEM,
            )
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            continue
        if files["improver.py"] == procedure:
            continue
        score = 0
        remaining = api.budget().get("trial_tasks", 0)
        if remaining:
            n = min(len(ctx["results"]), remaining)
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"] / max(1, result["n"])
                feedback += f"\nProposal {index + 1} trial: {result['solved']}/{result['n']} solved."
            except api.BudgetExceeded:
                pass
        if score > best_score:
            best, best_score = (files, note), score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
