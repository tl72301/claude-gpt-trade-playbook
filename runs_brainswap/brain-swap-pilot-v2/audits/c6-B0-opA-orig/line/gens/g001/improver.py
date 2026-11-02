"""Improvement procedure with budget-aware candidate trials."""

import re


SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from examples. "
    "Favor generalizable inference and use the available feedback carefully."
)
BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'
GUIDANCE = (
    "Known failure modes to address: (1) overfitting to shown examples instead of the underlying rule; "
    "(2) wrong output length or filtering logic; (3) off-by-one or sign/order errors; "
    "(4) unhandled edge cases such as empty input. Make the solver's check-and-revise loop "
    "use failing cases to re-derive the rule, not to patch them. The improver must also be changed."
)


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
    solved = sum(bool(item["passed"]) for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: solved {solved}/{len(ctx['results'])}.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory:\n{ctx.get('memory') or '(none)'}\n\n"
        f"{GUIDANCE}\n\n"
        "Rewrite both files to improve generalization to hidden tests. Diagnose "
        "systematic failure modes, not just individual examples. Preserve the contracts "
        "and respect API budgets. The improver must change too. Return each full file "
        'between lines <file name="NAME"> and </file>, followed by '
        "<note>one line for the next generation</note>."
    )
    best = None
    best_score = -1
    feedback = ""
    initial_budget = api.budget()
    trial_total = initial_budget.get("trial_tasks", 0)
    calls = initial_budget.get("llm_calls", 0)
    candidates = min(3, calls)
    trial_size = min(len(ctx["results"]), trial_total // max(1, candidates))
    for index in range(candidates):
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            feedback += "\nThe previous proposal omitted a required full file."
            continue
        if trial_size == 0:
            # No trial budget: keep the first complete, well-formed proposal.
            if best is None:
                best = (files, note)
            continue
        try:
            result = api.trial(files["solver.py"], trial_size)
        except api.BudgetExceeded:
            break
        score = result["solved"]
        feedback += (
            f"\nCandidate {index + 1} trial: {score}/{result['n']} solved. "
            "If this is weak, change the general strategy rather than adding special cases."
        )
        if score > best_score:
            best, best_score = (files, note), score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
