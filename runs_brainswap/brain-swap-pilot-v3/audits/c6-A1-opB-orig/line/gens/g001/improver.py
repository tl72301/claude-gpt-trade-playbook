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
        "not just the displayed tasks. Examine failed examples for ambiguities in "
        "ordering, duplicates, boundaries, and adjacent-element rules. Preserve "
        "successful behavior and respect API budgets. Make the improvement procedure "
        "use trial feedback effectively. Return full source for each file between "
        '<file name="NAME"> and </file> lines, followed by '
        "<note>one line for the next generation</note>."
    )
    best, top = None, -1
    feedback = ""
    for index in range(CANDIDATES):
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            feedback += f"\nCandidate {index + 1} omitted a required file."
            continue
        try:
            result = api.trial(files["solver.py"], TRIAL_TASKS)
            score = result["solved"]
            feedback += (
                f"\nCandidate {index + 1} trial result: {result!r}\n"
                "Propose a distinct improvement; retain general behavior that works."
            )
        except api.BudgetExceeded:
            if best is None:
                best = (files, note)
            break
        except Exception as exc:
            score = -1
            feedback += f"\nCandidate {index + 1} trial failed: {exc!r}"
        if best is None or score > top:
            best, top = (files, note), score
    if best is None:
        return {"files": {}, "note": "No usable proposal; preserve the current agent."}
    return {"files": best[0], "note": best[1]}
