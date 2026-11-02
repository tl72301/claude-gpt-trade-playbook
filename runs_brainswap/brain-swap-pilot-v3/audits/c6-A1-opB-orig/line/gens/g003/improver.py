import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver (writes Python functions from "
    "examples) and an improvement procedure (this program, which rewrites the agent)."
)
CANDIDATES = 3
TRIAL_TASKS = 6

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
        f"Memory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "Rewrite BOTH files while keeping their contracts. Improve generalization, "
        "not just the displayed tasks. Examine failed examples for ambiguities "
        "in ordering, duplicates, boundaries, stateful calculations, and "
        "adjacent-element rules. Do not hard-code task examples. Preserve "
        "successful behavior and respect API budgets. Make the improvement "
        "procedure use trial feedback effectively. Return full source for each "
        'file between <file name="NAME"> and </file> lines, followed by '
        "<note>one line for the next generation</note>."
    )

    baseline = {"solver.py": solver, "improver.py": procedure}
    best = (baseline, "Preserved the current agent; no trial improvement established.")
    top = None
    feedback = ""

    try:
        result = api.trial(solver, TRIAL_TASKS)
        top = result["solved"]
        feedback += f"\nCurrent solver baseline trial: {result!r}\n"
    except api.BudgetExceeded:
        feedback += "\nBaseline trial unavailable because of budget.\n"
    except Exception as exc:
        feedback += f"\nBaseline trial failed: {exc!r}\n"

    for index in range(CANDIDATES):
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            feedback += f"\nCandidate {index + 1} omitted a required file.\n"
            continue
        try:
            compile(files["solver.py"], "solver.py", "exec")
            compile(files["improver.py"], "improver.py", "exec")
        except Exception as exc:
            feedback += f"\nCandidate {index + 1} has invalid Python: {exc!r}\n"
            continue
        try:
            result = api.trial(files["solver.py"], TRIAL_TASKS)
            score = result["solved"]
            feedback += (
                f"\nCandidate {index + 1} solver:\n{files['solver.py']}\n"
                f"Trial result: {result!r}\n"
                "Use the feedback to propose a distinct improvement while "
                "preserving behavior that works. Small trial scores are noisy.\n"
            )
        except api.BudgetExceeded:
            if top is None:
                best = (files, note)
            break
        except Exception as exc:
            feedback += f"\nCandidate {index + 1} trial failed: {exc!r}\n"
            continue
        if top is None or score > top:
            best, top = (files, note), score

    return {"files": best[0], "note": best[1]}
