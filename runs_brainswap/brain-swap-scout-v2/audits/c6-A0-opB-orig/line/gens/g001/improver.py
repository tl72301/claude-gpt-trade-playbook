"""Improve the solver using failure analysis and optional candidate trials."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver that writes Python functions "
    "from examples, and an improvement procedure that rewrites the agent."
)
CANDIDATES = 2
TRIAL_TASKS = 12
NOTES = [
    "Distinguish value-based rules from index-based and neighbor-based rules.",
    "Hidden-test failures can indicate overfitting, boundary errors, or a plausible "
    "but incorrect rule even when all shown examples pass.",
    "Verify all shown examples and retry on actual check failures.",
    "Keep a top-level def f(xs), and respect available API budgets.",
]

BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    rest = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    note = re.search(r"<note>(.*?)</note>", rest, re.DOTALL)
    return files, (note.group(1).strip() if note else "")


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
        f"Generation {ctx['generation']}. The solver solved {solved} of "
        f"{len(ctx['results'])} development tasks.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        "Strategy notes:\n" + "".join(f"- {note}\n" for note in NOTES)
        + f"\nMemory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files to improve generalization on unseen tasks. Analyze "
        "failures for competing rules and edge cases, but do not hard-code task "
        "IDs or example answers. The solver should verify shown examples and retry "
        "when possible. Improve this procedure too, including lessons from results. "
        "Preserve both API contracts and use only the standard library. For each "
        "file, reply with a line "
        '<file name="NAME">, then the full source, then a line </file>. '
        "Finish with <note>one line for your next generation</note>."
    )
    best = None
    top = -1
    for index in range(CANDIDATES):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            request = prompt
            if index:
                request += (
                    "\nPropose a distinct strategy from earlier candidates; "
                    "prioritize robust generalization and budget safety."
                )
            reply = api.llm(request, system=SYSTEM)
            files, note = parse(reply)
            if "solver.py" not in files or "improver.py" not in files:
                continue
            if files["improver.py"] == procedure:
                continue
            score = 0
            if TRIAL_TASKS:
                try:
                    score = api.trial(files["solver.py"], TRIAL_TASKS)["solved"]
                except api.BudgetExceeded:
                    if best is not None:
                        break
            if score > top:
                best, top = (files, note), score
        except api.BudgetExceeded:
            break
    if best is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": best[0], "note": best[1]}
