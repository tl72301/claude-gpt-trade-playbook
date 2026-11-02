"""Propose and measure solver improvements while retaining future adaptability."""

import re

SYSTEM = (
    "You improve an AI agent that writes Python functions from examples. "
    "Diagnose generalizable failure modes and preserve both API contracts."
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
        status = "solved" if item["passed"] else "FAILED (" + str(item.get("failure")) + ")"
        lines.append(f"- {item['id']}: {status}")
        if not item["passed"]:
            for ex in item.get("examples", []):
                lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    results = ctx["results"]
    solved = sum(bool(r["passed"]) for r in results)
    no_f = sum(
        not r["passed"] and "no function f" in str(r.get("failure"))
        for r in results
    )
    prompt = (
        f"Generation {ctx['generation']}: {solved}/{len(results)} tasks solved; "
        f"{no_f} failures report no function f. Other failures may be wrong "
        "rules even when all shown examples pass.\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(results)}\n\n"
        f"Memory:\n{ctx.get('memory') or '(none)'}\n\n"
        "Propose a general improvement, not hardcoded task IDs or examples. "
        "Distinguish failures on shown examples from hidden-test generalization. "
        "Respect API budgets and contracts. Rewrite BOTH files; improver.py must "
        "change and should make future search or evaluation more effective. "
        "Return each full source between standalone lines "
        '<file name="NAME"> and </file>, followed by '
        "<note>one concise line for the next generation</note>."
    )
    budget = api.budget()
    calls = min(3, budget.get("llm_calls", 0))
    trial_budget = budget.get("trial_tasks", 0)
    trial_n = min(len(results), trial_budget // calls) if calls else 0
    best = None
    top = -1
    feedback = ""
    for _ in range(calls):
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not all(name in files and files[name].strip()
                   for name in ("solver.py", "improver.py")):
            feedback = "\nThe last proposal was missing a required full file. Include both."
            continue
        if files["improver.py"].strip() == procedure.strip():
            feedback = "\nThe improver must also be changed."
            continue
        score = 0
        if trial_n:
            try:
                trial = api.trial(files["solver.py"], trial_n)
                score = trial["solved"]
                feedback = (
                    f"\nThe most recent proposal solved {score}/{trial.get('n', trial_n)} "
                    "trial tasks. Seek a different general improvement if appropriate."
                )
            except api.BudgetExceeded:
                break
            except Exception as exc:
                feedback = f"\nThe last proposal failed trial: {exc!s}. Fix the code."
                continue
        if score > top:
            best, top = (files, note), score
    if best is None:
        return {"files": {}, "note": "No complete trialable proposal."}
    return {"files": best[0], "note": best[1] or f"Selected trial score {top}/{trial_n}."}
