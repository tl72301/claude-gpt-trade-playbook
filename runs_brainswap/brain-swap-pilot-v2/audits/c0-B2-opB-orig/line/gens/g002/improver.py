"""Budget-aware iterative improvement procedure."""

import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from examples. "
    "Favor generalizable changes and evaluate proposals when possible."
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
        f"Generation {ctx['generation']}: solved {solved}/{len(ctx['results'])}.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Earlier memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files, preserving their contracts. Improve hidden-test "
        "generalization without task-ID-specific solutions. Analyze failed "
        "examples for recurring ambiguity: boundaries, output order, original "
        "versus transformed values, and operation order. Preserve approaches "
        "that already work; avoid overfitting or needless complexity. Make the "
        "improver useful for subsequent generations. Return complete source "
        "for each file between standalone lines <file name=\"NAME\"> and "
        "</file>, then <note>one line for the next generation</note>."
    )
    best = None
    best_score = -1
    feedback = ""
    available = api.budget().get("trial_tasks", 0)
    # Use comparable trial sizes when the budget permits multiple proposals.
    n = min(len(ctx["results"]), available // 2) if available >= 2 else available
    for _ in range(3):
        if api.budget().get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not files.get("solver.py") or not files.get("improver.py"):
            feedback += "\nThe previous proposal omitted a required complete file."
            continue
        try:
            compile(files["solver.py"], "solver.py", "exec")
            compile(files["improver.py"], "improver.py", "exec")
        except SyntaxError as exc:
            feedback += f"\nThe previous proposal had a syntax error: {exc}"
            continue

        if n and api.budget().get("trial_tasks", 0) >= n:
            try:
                result = api.trial(files["solver.py"], n)
            except api.BudgetExceeded:
                n = 0
            else:
                score = result["solved"]
                feedback += (
                    f"\nA proposal solved {score}/{n} trial tasks. "
                    "Consider a different general approach if this is weak."
                )
                if score > best_score:
                    best, best_score = (files, note), score
                continue
        if best is None:
            best = (files, note)
        break

    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
