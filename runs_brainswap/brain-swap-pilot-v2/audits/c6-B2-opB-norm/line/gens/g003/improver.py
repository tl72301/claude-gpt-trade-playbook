"""Propose and trial general improvements to the solver."""

import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from examples. "
    "Design robust general-purpose improvements, not task-specific answers."
)
BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    remainder = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    match = re.search(r"<note>(.*?)</note>", remainder, re.DOTALL)
    return files, match.group(1).strip() if match else ""


def describe(results):
    lines = []
    for result in results:
        lines.append(
            f"- {result['id']}: "
            + ("solved" if result["passed"] else f"FAILED ({result['failure']})")
        )
        if not result["passed"]:
            for example in result["examples"]:
                lines.append(f"    f({example['input']!r}) == {example['output']!r}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    improver = api.source("improver.py")
    n = len(ctx["results"])
    solved = sum(result["passed"] for result in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: solved {solved}/{n}.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{improver}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Memory: {ctx['memory'] or '(none)'}\n\n"
        "Rewrite both files, preserving their contracts. Improve generalization to "
        "hidden examples, response parsing, budget handling, and the future "
        "improvement procedure. Failures may reflect ambiguous rules rather than "
        "code errors: reason about general failure modes, not task IDs or memorized "
        "examples. Preserve successful behavior. Return each complete source between "
        'lines <file name="NAME"> and </file>, followed by <note>one line</note>.'
    )
    best = None
    best_score = -1
    history = []

    for index in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            query = prompt
            if history:
                query += (
                    "\n\nPrevious proposal results:\n" + "\n".join(history)
                    + "\nAddress observed weaknesses or propose a materially "
                    "different general improvement while preserving what works."
                )
            response = api.llm(query, system=SYSTEM)
        except api.BudgetExceeded:
            break

        files, note = parse(response)
        if "solver.py" not in files or "improver.py" not in files:
            history.append(f"Proposal {index + 1}: missing required files.")
            continue
        try:
            compile(files["solver.py"], "solver.py", "exec")
            compile(files["improver.py"], "improver.py", "exec")
        except (SyntaxError, ValueError) as exc:
            history.append(f"Proposal {index + 1}: invalid Python: {exc}")
            continue

        score = None
        try:
            if n and api.budget().get("trial_tasks", 0) >= n:
                trial = api.trial(files["solver.py"], n)
                if trial["n"] == n:
                    score = trial["solved"]
                    history.append(
                        f"Proposal {index + 1}: solved {score}/{n}. Note: {note}"
                    )
                else:
                    history.append(f"Proposal {index + 1}: incomplete trial.")
            else:
                history.append(f"Proposal {index + 1}: no full trial available.")
        except api.BudgetExceeded:
            history.append(f"Proposal {index + 1}: trial budget exhausted.")
        except Exception as exc:
            history.append(f"Proposal {index + 1}: trial failed: {exc!r}")

        if best is None or (score is not None and score > best_score):
            best = (files, note)
            if score is not None:
                best_score = score

    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
