"""Propose and trial solver improvements while preserving the agent contracts."""

import ast
import re

SYSTEM = (
    "You improve an AI agent whose solver writes Python functions from examples. "
    "Respect both API contracts and the standard-library-only policy."
)
BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    rest = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    note = re.search(r"<note>(.*?)</note>", rest, re.DOTALL)
    return files, note.group(1).strip() if note else ""


def valid(files, old_procedure):
    if "solver.py" not in files or "improver.py" not in files:
        return False
    if files["improver.py"].strip() == old_procedure.strip():
        return False
    try:
        for name, entry in (("solver.py", "solve"), ("improver.py", "improve")):
            tree = ast.parse(files[name])
            if not any(isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and x.name == entry for x in tree.body):
                return False
    except (SyntaxError, ValueError, TypeError):
        return False
    return True


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
        f"Generation {ctx['generation']}: solved {solved}/{len(ctx['results'])}.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Improve generalization on hidden tests, not just shown examples. "
        "Respect the contracts and standard-library-only policy. Rewrite both files; "
        "the improver must change too. Return each full source between standalone "
        '<file name="NAME"> and </file> lines, then <note>one line</note>.'
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
        if not valid(files, procedure):
            feedback = "\nThe previous proposal was invalid. Return both complete, syntactically valid files."
            continue
        remaining = api.budget().get("trial_tasks", 0)
        score = 0
        if remaining:
            # Leave enough tasks to compare another candidate when possible.
            n = min(len(ctx["results"]), max(1, remaining // 2) if index == 0 else remaining)
            try:
                trial = api.trial(files["solver.py"], n)
                score = trial["solved"] / trial["n"] if trial["n"] else 0
                feedback = (
                    f"\nThe previous candidate solved {trial['solved']}/{trial['n']} "
                    "trial tasks. Propose a different general improvement."
                )
            except api.BudgetExceeded:
                feedback = "\nPropose a different general improvement."
        if best is None or score > best_score:
            best = (files, note)
            best_score = score
        if not api.budget().get("trial_tasks", 0):
            break
    if best is None:
        return {"files": {}, "note": "No valid proposal."}
    return {"files": best[0], "note": best[1]}
