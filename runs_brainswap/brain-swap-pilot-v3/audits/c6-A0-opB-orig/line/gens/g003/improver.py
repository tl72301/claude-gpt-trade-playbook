"""Generate and compare solver improvements using development trials."""

import re

SYSTEM = (
    "You improve an AI agent that writes Python functions from examples. "
    "Preserve the given contracts and avoid overfitting individual tasks."
)
CANDIDATES = 2
TRIAL_TASKS = 12

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
        f"Generation {ctx['generation']}: {solved}/{len(ctx['results'])} tasks solved.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Improve both files while preserving their contracts. Diagnose failure patterns "
        "from all available examples, but avoid task-specific lookup tables. Remember "
        "that checks cover shown examples only, not hidden tests. Make the improvement "
        "procedure select robust candidates rather than simply optimizing a noisy trial. "
        "Return each complete file between lines <file name=\"NAME\"> and </file>, "
        "followed by <note>one line for the next generation</note>."
    )
    best = None
    top = -1
    for index in range(CANDIDATES):
        try:
            reply = api.llm(
                prompt + f"\nProposal {index + 1}: explore a distinct general strategy.",
                system=SYSTEM,
            )
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            continue
        try:
            compile(files["solver.py"], "solver.py", "exec")
            compile(files["improver.py"], "improver.py", "exec")
        except (SyntaxError, ValueError, TypeError):
            continue
        try:
            score = api.trial(files["solver.py"], TRIAL_TASKS)["solved"]
        except api.BudgetExceeded:
            break
        except Exception:
            continue
        if score > top:
            best = (files, note)
            top = score
    if best is None:
        return {"files": {}, "note": "No valid, successfully trialed proposal."}
    return {"files": best[0], "note": best[1]}
