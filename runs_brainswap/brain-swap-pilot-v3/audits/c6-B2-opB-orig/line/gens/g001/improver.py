"""Budget-aware improvement procedure."""

import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from examples. "
    "Favor general solutions over memorization."
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
        "standard library and obey the documented APIs. Consider budget limits and "
        "avoid choosing an untested candidate over a tested candidate merely because "
        "trial budget was exhausted. For each file reply with a line "
        '<file name="NAME">, full source, and a line </file>. Finish with '
        "<note>one line for the next generation</note>."
    )
    best = None
    best_score = -1.0
    fallback = None
    feedback = ""
    initial_trials = api.budget().get("trial_tasks", 0)
    # Reserve comparable trial batches for multiple proposals when possible.
    batch = max(1, min(len(ctx["results"]), initial_trials // 2)) if initial_trials else 0
    for index in range(3):
        if api.budget().get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            feedback = "\nThe previous proposal omitted a required file."
            continue
        try:
            compile(files["solver.py"], "solver.py", "exec")
            compile(files["improver.py"], "improver.py", "exec")
        except (SyntaxError, ValueError):
            feedback = "\nThe previous proposal contained invalid Python."
            continue
        if fallback is None:
            fallback = (files, note)
        remaining = api.budget().get("trial_tasks", 0)
        if not batch or remaining < batch:
            feedback = "\nNo comparable trial budget remains."
            continue
        try:
            result = api.trial(files["solver.py"], batch)
        except api.BudgetExceeded:
            feedback = "\nTrial budget was exhausted."
            continue
        score = result["solved"] / max(1, result["n"])
        if score > best_score:
            best = (files, note)
            best_score = score
        feedback = (
            f"\nThe previous candidate solved {result['solved']} of "
            f"{result['n']} trial tasks. Propose a distinct improvement, "
            "especially for rules requiring multiple transformations."
        )
    choice = best or fallback
    if choice is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": choice[0], "note": choice[1]}
