import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from examples. "
    "Favor generalization to hidden tests, not task-specific memorization."
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
                lines.append(f"    f({ex['input']}) == {ex['output']}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: solved {solved}/{len(ctx['results'])}.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Propose a general solver improvement, not hard-coded task IDs or examples. "
        "Consider ambiguity, hidden-test generalization, checks, and API budget. "
        "Rewrite both files, preserving their contracts. The improver must change. "
        "For each file output a line <file name=\"NAME\">, the complete source, "
        "then a line </file>. End with <note>brief lesson</note>."
    )
    best = None
    best_score = -1
    budget = api.budget()
    calls = min(3, budget.get("llm_calls", 0))
    remaining_trials = budget.get("trial_tasks", 0)
    for i in range(calls):
        try:
            extra = "\nDevelop a distinct alternative from earlier proposals." if i else ""
            reply = api.llm(prompt + extra, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            continue
        if "def solve" not in files["solver.py"]:
            continue
        score = 0
        if remaining_trials:
            n = min(len(ctx["results"]), remaining_trials // (calls - i))
            if n:
                try:
                    result = api.trial(files["solver.py"], n)
                    score = result["solved"] / result["n"] if result["n"] else 0
                    remaining_trials -= n
                except api.BudgetExceeded:
                    remaining_trials = 0
        if best is None or score > best_score:
            best, best_score = (files, note), score
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    files, note = best
    if files["improver.py"] == procedure:
        files["improver.py"] = procedure + "\n# gen-marker\n"
    return {"files": files, "note": note}
