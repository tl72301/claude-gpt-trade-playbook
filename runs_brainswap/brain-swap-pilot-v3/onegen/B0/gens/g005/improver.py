"""Improve the solver and this procedure using development feedback and trials."""

import re

SYSTEM = (
    "You improve an AI agent whose solver writes Python functions from examples. "
    "Preserve the contracts and propose general improvements, not task-ID lookup."
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
    solved = sum(bool(item["passed"]) for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: {solved}/{len(ctx['results'])} solved.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Memory: {ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files, preserving their contracts. The solver should infer "
        "general transformations and handle hidden cases, not memorize task IDs. "
        "Use the failure patterns to guide improvements. The improver must change "
        "and should make later improvements more effective. Return each full file "
        'between lines <file name="NAME"> and </file>, then finish with '
        "<note>one line for the next generation</note>."
    )
    best = None
    best_score = -1
    for index in range(3):
        try:
            budget = api.budget()
            if budget.get("llm_calls", 0) <= 0:
                break
            extra = ""
            if index:
                extra = (
                    "\nPropose a meaningfully different approach from prior "
                    "candidates, prioritizing generalization and robust validation."
                )
            reply = api.llm(prompt + extra, system=SYSTEM)
            files, note = parse(reply)
            if "solver.py" not in files or "improver.py" not in files:
                continue
            if files["improver.py"] == procedure:
                continue
            score = 0
            remaining = api.budget().get("trial_tasks", 0)
            if remaining:
                n = min(len(ctx["results"]), remaining)
                score = api.trial(files["solver.py"], n)["solved"]
                prompt += f"\nCandidate {index + 1} trial: {score}/{n} solved."
            if best is None or score > best_score:
                best = (files, note)
                best_score = score
        except api.BudgetExceeded:
            break
    if best is None:
        return {"files": {}, "note": "No usable proposal; inspect budget and format."}
    return {"files": best[0], "note": best[1]}
