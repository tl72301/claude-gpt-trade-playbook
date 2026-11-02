"""Improvement procedure with budget-aware trials and feedback."""

import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from examples. "
    "Propose generalizable improvements, not solutions keyed to task IDs."
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
        lines.append(
            f"- {item['id']}: "
            + ("solved" if item["passed"] else f"FAILED ({item['failure']})")
        )
        if not item["passed"]:
            for ex in item["examples"]:
                lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(bool(item["passed"]) for item in ctx["results"])
    base = (
        f"Generation {ctx['generation']}: solved {solved}/{len(ctx['results'])}.\n"
        f"=== solver.py ===\n{solver}\n=== END ===\n"
        f"=== improver.py ===\n{procedure}\n=== END ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Earlier memory: {ctx['memory'] or '(none)'}\n\n"
        "Rewrite both files, preserving their contracts. Improve inference and "
        "generalization rather than hardcoding development tasks. The improver must "
        "change too. Account for API budgets and failures. Return full source as "
        '<file name="solver.py"> and <file name="improver.py"> blocks, each '
        "with opening and closing tags on separate lines, and a <note> for the "
        "next generation."
    )
    best = None
    best_score = -1
    feedback = []
    for index in range(3):
        try:
            budget = api.budget()
            if budget.get("llm_calls", 0) <= 0:
                break
            prompt = base
            if feedback:
                prompt += "\nPrevious proposal trial results:\n" + "\n".join(feedback)
                prompt += "\nTry a materially different approach if appropriate."
            reply = api.llm(prompt, system=SYSTEM)
            files, note = parse(reply)
            if "solver.py" not in files or "improver.py" not in files:
                feedback.append("Proposal omitted a required file.")
                continue
            if files["improver.py"] == procedure:
                feedback.append("Proposal did not change improver.py.")
                continue
            score = 0
            remaining = api.budget().get("trial_tasks", 0)
            if remaining:
                n = min(len(ctx["results"]), remaining)
                trial = api.trial(files["solver.py"], n)
                score = trial["solved"]
                feedback.append(f"Proposal {index + 1}: {score}/{trial['n']} trial tasks.")
            else:
                feedback.append(f"Proposal {index + 1}: not trialed.")
                if best is not None:
                    break
            if score > best_score:
                best, best_score = (files, note), score
            if remaining <= len(ctx["results"]):
                break
        except api.BudgetExceeded:
            break
        except Exception as exc:
            feedback.append(f"Proposal {index + 1} failed: {str(exc)[:200]}")
    if best is None:
        return {"files": {}, "note": "No usable proposal. " + " ".join(feedback)}
    return {"files": best[0], "note": best[1] + " " + " ".join(feedback)}
