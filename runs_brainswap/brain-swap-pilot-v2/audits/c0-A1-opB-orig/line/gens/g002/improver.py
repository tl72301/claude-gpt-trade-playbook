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
        "hidden inputs, not just consistency with shown examples. Investigate "
        "whether failures involve selection, output mapping, contextual relationships, "
        "operation order, or ambiguity. Consider resource limits and preserve the "
        "best validated candidate when retries fail. Do not hardcode task IDs or "
        "examples. The improver must change as well. Return full sources using tags "
        "on separate lines: <file name=\"solver.py\">, </file>, "
        "<file name=\"improver.py\">, </file>, followed by <note>one line</note>."
    )
    best = None
    top = -1
    feedback = ""
    for attempt in range(3):
        if api.budget().get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
            files, note = parse(reply)
            if "solver.py" not in files or "improver.py" not in files:
                feedback += "\nThe previous proposal omitted a required file."
                continue
            try:
                compile(files["solver.py"], "solver.py", "exec")
                compile(files["improver.py"], "improver.py", "exec")
            except SyntaxError as exc:
                feedback += f"\nThe previous proposal had a syntax error: {exc}"
                continue
            remaining = api.budget().get("trial_tasks", 0)
            if remaining:
                # Reserve comparable trials for later proposals when possible.
                slots = 3 - attempt
                n = min(len(ctx["results"]), max(1, remaining // slots))
                result = api.trial(files["solver.py"], n)
                score = result["solved"] / max(1, result["n"])
                feedback += (
                    f"\nCandidate {attempt + 1} scored {result['solved']}/"
                    f"{result['n']} in a trial. Seek a distinct general improvement "
                    "without overfitting these results."
                )
                if best is None or score > top:
                    best, top = (files, note), score
            elif best is None:
                best = (files, note)
                break
            else:
                break
        except api.BudgetExceeded:
            break
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
