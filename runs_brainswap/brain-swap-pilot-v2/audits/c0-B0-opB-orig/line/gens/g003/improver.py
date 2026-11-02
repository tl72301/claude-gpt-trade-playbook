"""Improve the solver and this procedure, optionally comparing proposals by trial."""

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
                lines.append(f"    f({ex['input']}) == {ex['output']}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: solved {solved}/{len(ctx['results'])}.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory: {ctx['memory'] or '(none)'}\n\n"
        "Rewrite both files, preserving their contracts. The solver must generalize "
        "to hidden cases, not memorize task IDs or examples. Diagnose failed examples "
        "by comparing plausible rules and identifying counterexamples; do not assume "
        "a rule is correct merely because it fits a few examples. Improve inference "
        "and validation without sacrificing solved tasks. The improver must also "
        "change or the proposal is discarded. Consider budget limits and use trials "
        "when useful. Return each complete source between lines "
        '<file name="NAME"> and </file>, followed by <note>one line</note>.'
    )
    best = None
    best_score = -1
    feedback = ""
    for index in range(3):
        if api.budget().get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            feedback += "\nA previous proposal omitted a required file. Return both complete files."
            continue
        if files["improver.py"].strip() == procedure.strip():
            feedback += "\nThe improver must actually change."
            continue
        score = 0
        remaining = api.budget().get("trial_tasks", 0)
        if remaining:
            try:
                result = api.trial(files["solver.py"], min(remaining, len(ctx["results"])))
                score = result["solved"] / max(1, result["n"])
                feedback += (
                    f"\nProposal {index + 1} trial: {result['solved']}/{result['n']} solved. "
                    "Try a materially different approach if proposing again."
                )
            except api.BudgetExceeded:
                pass
        if best is None or score > best_score:
            best, best_score = (files, note), score
        if api.budget().get("trial_tasks", 0) <= 0:
            break
    if best is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": best[0], "note": best[1]}
