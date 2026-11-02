"""Improve the solver and improvement procedure using observed results."""
import re

SYSTEM = (
    "You improve a Python program synthesis agent. Design general solutions, "
    "avoid overfitting task IDs, and respect the supplied API contracts."
)
BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    files = {k: v for k, v in files.items() if k in ("solver.py", "improver.py")}
    rest = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    match = re.search(r"<note>(.*?)</note>", rest, re.DOTALL)
    return files, match.group(1).strip() if match else ""


def describe(results):
    lines = []
    for item in results:
        lines.append(
            f"- {item['id']}: "
            + ("solved" if item["passed"] else f"FAILED ({item['failure']})")
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
        f"=== solver.py ===\n{solver}\n=== END ===\n\n"
        f"=== improver.py ===\n{procedure}\n=== END ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory: {ctx['memory'] or '(none)'}\n\n"
        "Propose a general improvement for hidden-test generalization. "
        "Analyze the failed examples for broadly useful hypothesis families, "
        "but do not specialize to task IDs or memorize examples. Checks only "
        "verify supplied examples, not hidden cases. Consider independent "
        "hypotheses, output-length analysis, arithmetic and critical review. "
        "Handle exhausted budgets gracefully. Rewrite both files with full "
        "source; the improver must change for the proposal to be accepted. "
        "Preserve contracts and use only the standard library. Output each "
        "source between standalone "
        '<file name="solver.py"> or <file name="improver.py"> and </file> lines, '
        "then <note>one concise note</note>."
    )
    best = None
    best_score = -1
    feedback = ""
    for _ in range(3):
        if api.budget().get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            feedback += "\nThe previous proposal omitted a required complete file."
            continue
        if files["improver.py"].strip() == procedure.strip():
            feedback += "\nThe previous improver was unchanged; change it."
            continue
        score = 0
        budget = api.budget()
        trial_tasks = budget.get("trial_tasks", 0)
        if trial_tasks:
            remaining_calls = budget.get("llm_calls", 0)
            n = min(
                len(ctx["results"]),
                max(1, trial_tasks // (2 if remaining_calls else 1)),
            )
            try:
                trial = api.trial(files["solver.py"], n)
                score = trial["solved"] / max(1, trial["n"])
                feedback += (
                    f"\nA previous candidate solved {trial['solved']}/{trial['n']} "
                    "trial tasks. If weak, try a materially different general "
                    "strategy; do not optimize for task identifiers."
                )
            except api.BudgetExceeded:
                pass
        if score > best_score:
            best = (files, note)
            best_score = score
    if best is None:
        return {"files": {}, "note": "No complete proposal generated."}
    return {"files": best[0], "note": best[1]}
