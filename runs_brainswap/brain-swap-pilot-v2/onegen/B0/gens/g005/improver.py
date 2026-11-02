"""Iterative improvement procedure with budget-aware candidate trials."""

import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from examples. "
    "Design general improvements rather than memorizing task IDs or examples."
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
        for ex in item.get("examples", []):
            lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: solved {solved}/{len(ctx['results'])}.\n"
        f"=== solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Earlier memory:\n{ctx.get('memory') or '(none)'}\n\n"
        "Rewrite BOTH files while keeping their contracts. Improve generalization "
        "to hidden examples, not just fitting shown examples. Use budgets wisely; "
        "api.check tests only shown examples. Consider competing hypotheses, edge "
        "cases and validation. The improver must also change; use trials when "
        "available and preserve useful feedback for later generations. "
        "Return each full source as a tag on its own line: "
        '<file name="solver.py">, source, </file>, and likewise for improver.py. '
        "Finish with <note>one concise line</note>."
    )
    best = None
    top = -1
    feedback = []
    for index in range(3):
        budget = api.budget()
        if budget.get("llm_calls", 0) <= 0:
            break
        request = prompt
        if feedback:
            request += "\nTrial feedback on prior proposals:\n" + "\n".join(feedback)
            request += "\nPropose a different, stronger general strategy."
        try:
            reply = api.llm(request, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            feedback.append(f"Proposal {index + 1}: missing required files.")
            continue
        if files["improver.py"] == procedure:
            feedback.append(f"Proposal {index + 1}: improver unchanged.")
            continue
        remaining = api.budget().get("trial_tasks", 0)
        score = 0
        if remaining:
            n = min(len(ctx["results"]), remaining)
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"] / max(1, result["n"])
                feedback.append(
                    f"Proposal {index + 1}: {result['solved']}/{result['n']} trial tasks."
                )
            except api.BudgetExceeded:
                feedback.append(f"Proposal {index + 1}: trial budget exhausted.")
            except Exception as exc:
                feedback.append(f"Proposal {index + 1}: trial error {exc!s}.")
                score = -1
        if score > top:
            best, top = (files, note), score
        if not api.budget().get("trial_tasks", 0) and best is not None:
            break
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
