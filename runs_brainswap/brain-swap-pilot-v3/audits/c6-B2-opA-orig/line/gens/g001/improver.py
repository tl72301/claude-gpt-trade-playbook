"""Improvement procedure with budget-aware candidate trials."""

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
        f"Generation {ctx['generation']}. The solver solved {solved} of "
        f"{len(ctx['results'])} development tasks.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite both files while preserving their contracts. Improve generalization "
        "to unseen inputs, not just consistency with shown examples. Do not hardcode "
        "task IDs or example answers. The improver must change too. Use only the "
        "standard library and obey the documented API. For each file reply with a "
        'line <file name="NAME">, full source, and a line </file>. Finish with '
        "<note>one line for the next generation</note>."
    )
    best = None
    best_score = -1
    feedback = ""
    for index in range(3):
        budget = api.budget()
        if budget.get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            feedback = "\nThe previous proposal did not contain both required files."
            continue
        try:
            compile(files["solver.py"], "solver.py", "exec")
            compile(files["improver.py"], "improver.py", "exec")
        except (SyntaxError, ValueError):
            feedback = "\nThe previous proposal contained invalid Python."
            continue
        score = 0
        remaining = api.budget().get("trial_tasks", 0)
        if remaining:
            n = min(remaining, len(ctx["results"]))
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"] / max(1, result["n"])
                feedback = (
                    f"\nA previous candidate solved {result['solved']} of "
                    f"{result['n']} trial tasks. Propose a distinct improvement."
                )
            except api.BudgetExceeded:
                pass
        if score > best_score:
            best = (files, note)
            best_score = score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
