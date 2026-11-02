import re

SYSTEM = (
    "You improve an AI agent that writes Python functions from examples. "
    "Favor general improvements and preserve the stated API contracts."
)
CANDIDATES = 3
TRIAL_TASKS = 8

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
                lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    base = (
        f"Generation {ctx['generation']}: {solved}/{len(ctx['results'])} tasks solved.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory: {ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files, preserving their contracts. Improve generalization to "
        "hidden tests, not just the shown examples. Use checks for debugging shown "
        "examples, but remember that passing them does not establish the hidden rule. "
        "Respect API budgets and handle exhaustion. Improve the proposal and trial "
        "procedure as well. Return each complete source between a line "
        '<file name="NAME"> and a line </file>, then <note>one line</note>.'
    )
    best = None
    top = -1
    feedback = []
    for index in range(CANDIDATES):
        prompt = base + (
            "\n\nCandidate direction: "
            + [
                "Improve rule inference and ambiguity handling.",
                "Improve verification and repair while conserving budget.",
                "Explore a different general approach from prior proposals.",
            ][index % 3]
        )
        if feedback:
            prompt += "\nEarlier trial feedback:\n" + "\n".join(feedback)
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            feedback.append(f"Candidate {index + 1}: missing required file.")
            continue
        try:
            result = api.trial(files["solver.py"], TRIAL_TASKS)
            score = result["solved"]
            feedback.append(f"Candidate {index + 1}: trial solved {score}.")
        except api.BudgetExceeded:
            if best is None:
                best = (files, note)
            break
        except Exception as exc:
            feedback.append(f"Candidate {index + 1}: trial error {type(exc).__name__}.")
            continue
        if score > top:
            best, top = (files, note), score
    if best is None:
        return {"files": {}, "note": "No usable proposal; preserve current files."}
    return {"files": best[0], "note": best[1]}
