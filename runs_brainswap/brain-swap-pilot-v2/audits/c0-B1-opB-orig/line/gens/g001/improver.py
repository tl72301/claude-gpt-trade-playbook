"""Propose and, when budget permits, compare solver improvements."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver that writes Python functions "
    "from examples, and an improvement procedure that rewrites the agent."
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
        f"Generation {ctx['generation']}: solved {solved}/{len(ctx['results'])}.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Propose a general improvement to the solver, not task-ID-specific "
        "memorization. Preserve the contracts and standard-library-only policy. "
        "Shown checks do not measure hidden generalization: address ambiguous "
        "rules and edge cases as well as example consistency. Also rewrite "
        "improver.py to improve future iterations; it must actually change. "
        "Return complete source for BOTH files, each enclosed by standalone "
        '<file name="NAME"> and </file> lines, followed by '
        "<note>one concise line</note>."
    )

    best = None
    best_score = -1
    feedback = ""
    budget = api.budget()
    calls = min(3, budget.get("llm_calls", 0))
    trial_total = budget.get("trial_tasks", 0)
    # Compare proposals on equally sized trials.
    trial_n = min(len(ctx["results"]), trial_total // max(1, calls))
    for _ in range(calls):
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            feedback = "\nThe previous proposal omitted a required complete file."
            continue
        if files["improver.py"] == procedure:
            feedback = "\nThe previous proposal did not change improver.py."
            continue
        try:
            compile(files["solver.py"], "solver.py", "exec")
            compile(files["improver.py"], "improver.py", "exec")
        except (SyntaxError, ValueError, TypeError) as exc:
            feedback = f"\nThe previous proposal did not compile: {exc}"
            continue
        if trial_n:
            try:
                result = api.trial(files["solver.py"], trial_n)
                score = result["solved"]
                feedback = (
                    f"\nThe previous proposal solved {score}/{result['n']} trial "
                    "tasks. Consider a different general approach."
                )
            except api.BudgetExceeded:
                score = -1
        else:
            score = 0
        if best is None or score > best_score:
            best, best_score = (files, note), score
    if best is None:
        return {"files": {}, "note": "No usable proposal"}
    return {"files": best[0], "note": best[1]}
