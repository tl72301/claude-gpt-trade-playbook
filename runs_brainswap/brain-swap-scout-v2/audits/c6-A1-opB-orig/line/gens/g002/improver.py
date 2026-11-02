"""Iteratively propose and trial solver improvements."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver that writes Python functions "
    "from examples, and an improvement procedure that rewrites the agent."
)
BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    rest = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    match = re.search(r"<note>(.*?)</note>", rest, re.DOTALL)
    return files, match.group(1).strip() if match else ""


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
        f"=== solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Memory: {ctx['memory'] or '(none)'}\n"
        "Improve generalization on hidden tests, not just shown examples. "
        "Analyze ambiguous rules and length-changing transformations. "
        "Do not hardcode task IDs or examples. Respect both contracts and use "
        "only the standard library; no file, network, or process access. "
        "Rewrite BOTH files, including a meaningful improvement to improver.py. "
        "Return each complete source between lines <file name=\"NAME\"> and "
        "</file>, followed by <note>one concise line</note>."
    )
    best = None
    best_score = -1
    feedback = ""
    for index in range(3):
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not all(name in files for name in ("solver.py", "improver.py")):
            feedback += "\nThe last proposal omitted a required complete file."
            continue
        if files["improver.py"] == procedure:
            feedback += "\nThe last proposal did not change improver.py."
            continue
        score = 0
        budget = api.budget()
        available = budget.get("trial_tasks", 0)
        if available:
            n = min(len(ctx["results"]), available)
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"]
                feedback += (
                    f"\nProposal {index + 1} trial: {score}/{result['n']} solved. "
                    "Try a different general strategy if this result is weak."
                )
            except api.BudgetExceeded:
                pass
        if best is None or score > best_score:
            best = (files, note)
            best_score = score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
