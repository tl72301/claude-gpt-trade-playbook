"""Iteratively improve the solver and its improvement procedure."""
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
        lines.append(
            f"- {item['id']}: " +
            ("solved" if item["passed"] else f"FAILED ({item['failure']})")
        )
        if not item["passed"]:
            for ex in item["examples"]:
                lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}. Solved {solved}/{len(ctx['results'])}.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Analyze failure patterns and propose a general improvement, not "
        "task-ID-specific solutions or memorization. Distinguish invalid code "
        "and failures on shown examples from rules that fit examples but "
        "generalize poorly. Preserve both contracts. Rewrite BOTH files; "
        "improver.py must actually change for acceptance. Use available solver "
        "and improvement budgets judiciously. For each file output a line "
        "<file name=\"NAME\">, its complete source, and a line </file>. "
        "Finish with <note>one line</note>."
    )
    best = None
    best_score = -1
    feedback = ""
    for index in range(3):
        budget = api.budget()
        if budget.get("llm_calls", 0) <= 0:
            break
        extra = ""
        if index:
            extra = (
                "\nPropose a substantially different strategy from earlier "
                "candidates. Prior trial feedback:\n" + feedback
            )
        try:
            reply = api.llm(prompt + extra, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not files.get("solver.py") or not files.get("improver.py"):
            feedback += "\nA proposal was missing a required file."
            continue
        if files["improver.py"] == procedure:
            feedback += "\nA proposal did not change improver.py."
            continue
        try:
            compile(files["solver.py"], "solver.py", "exec")
            compile(files["improver.py"], "improver.py", "exec")
        except (SyntaxError, ValueError, TypeError) as exc:
            feedback += f"\nA proposal did not compile: {exc}"
            continue
        remaining = api.budget().get("trial_tasks", 0)
        score = -1
        if remaining:
            n = min(remaining, len(ctx["results"]))
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"] / max(1, result["n"])
                feedback += (
                    f"\nCandidate {index + 1}: "
                    f"{result['solved']}/{result['n']} solved."
                )
            except api.BudgetExceeded:
                feedback += f"\nCandidate {index + 1}: trial budget exceeded."
        if best is None or score > best_score:
            best, best_score = (files, note), score
        if remaining and api.budget().get("trial_tasks", 0) == 0:
            break
    if best is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": best[0], "note": best[1]}
