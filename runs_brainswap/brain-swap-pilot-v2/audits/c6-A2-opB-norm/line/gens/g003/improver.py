"""Improve the solver using failure-focused proposals and development trials."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver that writes Python "
    "functions from examples and an improvement procedure that rewrites it."
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
                lines.append(f"    f({example['input']}) == {example['output']}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    improver = api.source("improver.py")
    results = ctx["results"]
    solved = sum(bool(r["passed"]) for r in results)
    prompt = (
        f"Generation {ctx['generation']}: solved {solved}/{len(results)} tasks.\n"
        f"Results:\n{describe(results)}\n\n"
        f"Memory: {ctx.get('memory') or '(none)'}\n\n"
        f"=== solver.py ===\n{solver}\n=== END ===\n\n"
        f"=== improver.py ===\n{improver}\n=== END ===\n\n"
        "Propose complete rewrites of BOTH files, preserving their contracts. "
        "The solver must improve generalization on hidden tests, not memorize "
        "task IDs or examples. Diagnose the actual failure pattern and consider "
        "ordering, filtering, indices, and ambiguous rules. Use checks to catch "
        "shown-example failures, but remember that passing shown examples does "
        "not guarantee the inferred rule is correct. Preserve robust budget "
        "handling. Improve the improvement procedure too; it must change for "
        "the proposal to be accepted. Return each complete source between "
        '<file name="solver.py"> or <file name="improver.py"> and </file> '
        "tags on their own lines, followed by <note>one line</note>."
    )
    best = None
    best_score = -1
    history = []
    for _ in range(3):
        budget = api.budget()
        if budget.get("llm_calls", 0) <= 0:
            break
        trial_remaining = budget.get("trial_tasks", 0) or 0
        try:
            text = api.llm(
                prompt + ("\nPrevious proposal trials:\n" + "\n".join(history) if history else ""),
                system=SYSTEM,
            )
        except api.BudgetExceeded:
            break
        files, note = parse(text)
        if "solver.py" not in files or "improver.py" not in files:
            history.append("A proposal was missing a required complete file.")
            continue
        if files["improver.py"] == improver:
            history.append("A proposal did not change improver.py.")
            continue
        if trial_remaining:
            # Use a broad sample rather than ranking on only a few tasks.
            n = min(len(results), trial_remaining)
            try:
                trial = api.trial(files["solver.py"], n)
                score = trial["solved"]
                history.append(f"Trial solved {score}/{trial['n']}. Proposal note: {note}")
            except api.BudgetExceeded:
                score = -1
            except Exception as exc:
                history.append(f"Trial failed: {exc}")
                continue
        else:
            score = -1
        if best is None or score > best_score:
            best = (files, note)
            best_score = score
        # An untested candidate should not displace a tested one.
        if not (api.budget().get("trial_tasks", 0) or 0):
            break
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
