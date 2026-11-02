"""Propose and compare general improvements to the synthesis agent."""

import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from examples. "
    "Optimize hidden-test generalization, not memorization of development tasks."
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
            for ex in item.get("examples", []):
                lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    results = ctx["results"]
    solved = sum(item["passed"] for item in results)
    prompt = (
        f"Generation {ctx['generation']}: {solved}/{len(results)} solved.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(results)}\n"
        f"Memory:\n{ctx.get('memory') or '(none)'}\n\n"
        "Rewrite BOTH files, preserving their contracts. Improve hidden-test "
        "generalization without hardcoding task IDs or examples. Diagnose "
        "ambiguity, systematic example validation, index/value confusion, "
        "cumulative state, boundary cases and exhausted budgets. In particular, "
        "consider competing rules that agree on the shown examples but disagree "
        "on zero, sign, divisibility, short inputs, or index origins. Checks "
        "validate only shown examples, not generalization. Preserve checked "
        "solutions if later attempts fail. Compare trial proposals on equal task "
        "counts and use budget judiciously. The improver must change too. Output "
        "complete sources between <file name=\"NAME\"> and </file> lines, "
        "followed by <note>one line of useful advice for the next generation</note>."
    )

    try:
        calls = min(2, api.budget().get("llm_calls", 0))
    except Exception:
        calls = 1

    candidates = []
    for index in range(calls):
        try:
            extra = (
                "\nDevelop a distinct general strategy, not a superficial variation."
                if index else ""
            )
            files, note = parse(api.llm(prompt + extra, system=SYSTEM))
            if not all(name in files for name in ("solver.py", "improver.py")):
                continue
            for name in ("solver.py", "improver.py"):
                compile(files[name], name, "exec")
            candidates.append((files, note))
        except api.BudgetExceeded:
            break
        except Exception:
            continue

    if not candidates:
        return {"files": {}, "note": "No usable proposal; inspect budgets and parsing."}

    try:
        remaining = api.budget().get("trial_tasks", 0)
        count = min(len(results), remaining // (len(candidates) + 1))
    except Exception:
        count = 0

    if count:
        try:
            baseline = api.trial(solver, count)["solved"]
        except Exception:
            baseline = None
        scored = []
        for files, note in candidates:
            try:
                score = api.trial(files["solver.py"], count)["solved"]
                scored.append((score, files, note))
            except api.BudgetExceeded:
                break
            except Exception:
                continue
        if scored:
            score, files, note = max(scored, key=lambda item: item[0])
            if baseline is None or score >= baseline:
                return {"files": files, "note": note}
            return {
                "files": {},
                "note": "Equal-sized trials favored the incumbent; seek a more robust strategy.",
            }

    files, note = candidates[0]
    return {"files": files, "note": note}
