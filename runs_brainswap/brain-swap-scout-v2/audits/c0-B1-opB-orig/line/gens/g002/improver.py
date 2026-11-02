"""Propose and compare improvements to the solver and improvement procedure."""
import re

SYSTEM = (
    "You improve an AI agent. Its solver writes Python functions from examples, "
    "and its improvement procedure rewrites the agent."
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
        lines.append(
            f"- {item['id']}: "
            + ("solved" if item["passed"] else f"FAILED ({item['failure']})")
        )
        if not item["passed"]:
            for ex in item["examples"]:
                lines.append(f"    f({ex['input']}) == {ex['output']}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: solved {solved} of "
        f"{len(ctx['results'])} development tasks.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Earlier memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite both files, preserving their contracts. Improve generalization "
        "rather than hard-coding task identifiers or examples. The solver can "
        "use api.check to validate shown examples, but hidden cases require "
        "careful rule inference. The improver must change too; make it better "
        "at comparing proposals within its available budget. Respect the "
        "standard-library-only sandbox and avoid file, network, or process access. "
        "Return each complete file between standalone lines "
        '<file name="NAME"> and </file>, followed by <note>one line</note>.'
    )
    budget = api.budget()
    calls = min(3, budget.get("llm_calls", 0))
    trial_budget = budget.get("trial_tasks", 0)
    n = min(len(ctx["results"]), trial_budget // max(1, calls))
    if n < 4:
        n = 0
    best = None
    top = -1
    feedback = ""
    for index in range(calls):
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            feedback += "\nThe last proposal omitted a required complete file."
            continue
        if files["improver.py"] == procedure:
            feedback += "\nThe last proposal did not change improver.py."
            continue
        score = 0
        if n and api.budget().get("trial_tasks", 0) >= n:
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"]
                feedback += (
                    f"\nProposal {index + 1} trial: {score}/{result['n']} solved. "
                    "Try a materially different general approach if this is weak."
                )
            except api.BudgetExceeded:
                pass
        if score > top:
            best = (files, note)
            top = score
    if best is None:
        return {"files": {}, "note": "No usable proposal generated."}
    return {"files": best[0], "note": best[1]}
