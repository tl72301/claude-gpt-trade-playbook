"""Improve the solver using feedback and budget-aware candidate trials."""
import re

SYSTEM = (
    "You improve an AI agent that writes Python functions from input/output examples. "
    "Propose general improvements rather than memorizing development tasks."
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
        f"=== solver.py ===\n{solver}\n=== improver.py ===\n{procedure}\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Memory: {ctx['memory'] or '(none)'}\n\n"
        "Rewrite both files, preserving their contracts. Improve generalization to "
        "hidden inputs, not just consistency with shown examples. Investigate failure "
        "patterns, ambiguous transformations, and resource limits. Do not hardcode "
        "task IDs or examples. The improver must change as well. Return full sources "
        "using tags on separate lines: <file name=\"solver.py\">, </file>, "
        "<file name=\"improver.py\">, </file>, followed by <note>one line</note>."
    )
    best = None
    top = -1
    feedback = ""
    for _ in range(3):
        if api.budget().get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
            files, note = parse(reply)
            if "solver.py" not in files or "improver.py" not in files:
                feedback += "\nThe previous proposal omitted a required file."
                continue
            remaining = api.budget().get("trial_tasks", 0)
            if remaining:
                n = min(len(ctx["results"]), remaining)
                result = api.trial(files["solver.py"], n)
                score = result["solved"] / max(1, result["n"])
                feedback += (
                    f"\nA candidate scored {result['solved']}/{result['n']} in a trial. "
                    "Consider a different general strategy for the next candidate."
                )
            else:
                score = 0
            if best is None or score > top:
                best, top = (files, note), score
            if not api.budget().get("trial_tasks", 0):
                break
        except api.BudgetExceeded:
            break
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
