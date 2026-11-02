"""Improve the solver and retain a procedure for comparing future proposals."""
import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver that writes Python functions "
    "from examples, and an improvement procedure that rewrites the agent."
)
BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    remainder = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    note = re.search(r"<note>(.*?)</note>", remainder, re.DOTALL)
    return files, note.group(1).strip() if note else ""


def describe(results):
    lines = []
    for result in results:
        if result["passed"]:
            lines.append(f"- {result['id']}: solved")
        else:
            lines.append(f"- {result['id']}: FAILED ({result['failure']})")
            for example in result["examples"]:
                lines.append(
                    f"    f({example['input']!r}) == {example['output']!r}"
                )
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    improver = api.source("improver.py")
    solved = sum(r["passed"] for r in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: {solved}/{len(ctx['results'])} solved.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{improver}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite both files while preserving their contracts and the standard-library "
        "policy. Improve hidden-test generalization, not just example matching. "
        "Avoid hardcoding task IDs or individual examples. The improver must change "
        "for a proposal to be eligible. Return each full source between lines "
        '<file name="NAME"> and </file>, then <note>one line</note>.'
    )
    best = None
    best_score = -1
    feedback = ""
    for _ in range(3):
        if api.budget().get("llm_calls", 0) <= 0:
            break
        try:
            response = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(response)
        if "solver.py" not in files or "improver.py" not in files:
            feedback += "\nThe last proposal was missing a required file."
            continue
        if files["improver.py"] == improver:
            feedback += "\nThe improver must also change."
            continue
        score = 0
        remaining = api.budget().get("trial_tasks", 0)
        if remaining:
            n = min(remaining, len(ctx["results"]))
            try:
                trial = api.trial(files["solver.py"], n)
                score = trial["solved"] / max(trial["n"], 1)
                feedback += (
                    f"\nA previous proposal scored {trial['solved']}/{trial['n']} "
                    "in a trial. Seek a more general improvement."
                )
            except api.BudgetExceeded:
                pass
        if best is None or score > best_score:
            best, best_score = (files, note), score
        if not api.budget().get("trial_tasks", 0):
            break
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
