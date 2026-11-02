"""Propose and, when budget permits, trial improvements to the solver."""

import re

SYSTEM = (
    "You improve an AI agent that writes Python functions from input/output "
    "examples. Prioritize generalization to hidden tests and preserve the contracts."
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
                lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: {solved}/{len(ctx['results'])} solved.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        f"Memory:\n{ctx['memory'] or '(none)'}\n\n"
        "Propose a general solver improvement, not task-ID-specific patches. "
        "Analyze failed examples for likely ambiguity or reasoning errors. "
        "Respect runtime budgets and both file contracts. Rewrite both files: "
        "improver.py must change for the proposal to be eligible. "
        "Use <file name=\"solver.py\"> and <file name=\"improver.py\"> tags "
        "on separate lines around the complete source of each file, and end "
        "with <note>one concise line for the next generation</note>."
    )
    best = None
    best_score = -1
    for index in range(3):
        if api.budget().get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            continue
        if files["improver.py"] == procedure:
            continue
        remaining = api.budget().get("trial_tasks", 0)
        n = min(len(ctx["results"]), remaining)
        score = 0
        if n:
            try:
                result = api.trial(files["solver.py"], n)
                score = result["solved"] / max(1, result["n"])
            except api.BudgetExceeded:
                pass
        if score > best_score:
            best, best_score = (files, note), score
        if n:
            prompt += (
                f"\n\nCandidate {index + 1} trial: {score:.3f} solved fraction "
                f"on {n} tasks. Propose a different general approach if useful."
            )
        else:
            break
    if best is None:
        return {"files": {}, "note": "No usable proposal."}
    return {"files": best[0], "note": best[1]}
