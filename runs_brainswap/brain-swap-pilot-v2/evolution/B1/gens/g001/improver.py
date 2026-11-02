"""Improve the solver and the improvement procedure using development feedback."""

import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from examples. "
    "Optimize hidden-test generalization, not memorization of development tasks."
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
        lines.append(
            f"- {item['id']}: "
            + ("solved" if item["passed"] else f"FAILED ({item['failure']})")
        )
        if not item["passed"]:
            for ex in item.get("examples", []):
                lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: {solved}/{len(ctx['results'])} solved.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Memory:\n{ctx.get('memory') or '(none)'}\n\n"
        "Rewrite BOTH files, preserving their contracts. Improve generalization "
        "across tasks; do not hardcode task IDs or examples. Consider inference "
        "ambiguity, example checks, budget limits, and robust code extraction. "
        "The improver must change too. Output each complete source between a "
        'line <file name="NAME"> and a line </file>, followed by '
        "<note>one line of useful advice for the next generation</note>."
    )
    candidates = []
    for index in range(2):
        try:
            budget = api.budget()
            if budget.get("llm_calls", 0) <= 0:
                break
            extra = (
                "\nExplore a distinct strategy from the previous proposal."
                if index else ""
            )
            reply = api.llm(prompt + extra, system=SYSTEM)
            files, note = parse(reply)
            if "solver.py" not in files or "improver.py" not in files:
                continue
            score = -1
            trial_budget = api.budget().get("trial_tasks", 0)
            if trial_budget:
                n = min(len(ctx["results"]), max(1, trial_budget // (2 - index)))
                score = api.trial(files["solver.py"], n)["solved"] / n
            candidates.append((score, files, note))
        except api.BudgetExceeded:
            break
        except Exception:
            continue
    if not candidates:
        return {"files": {}, "note": "No usable proposal; reconsider the prompt or budgets."}
    _, files, note = max(candidates, key=lambda item: item[0])
    return {"files": files, "note": note}
