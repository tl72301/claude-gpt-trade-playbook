"""Improve the solver and the improvement procedure using development feedback."""

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
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: {solved}/{len(ctx['results'])} solved.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Memory:\n{ctx.get('memory') or '(none)'}\n\n"
        "Rewrite BOTH files, preserving their contracts. Improve generalization "
        "without hardcoding task IDs or examples.\n"
        "Diagnosis guide:\n"
        "- Many failures show a constant or sentinel output (e.g. all -1 or all []): the "
        "solver is giving up or defaulting; require an actual rule and never a fallback "
        "that ignores the input.\n"
        "- Near-zero hidden scores with shown examples fitting: the rule overfits. Prefer "
        "rules whose mechanism is explained by every example, and verify by hand-tracing "
        "several examples before answering.\n"
        "- Index/value confusion and off-by-one errors: the prompt should ask the model to "
        "state which index or value each output element uses.\n"
        "- Ambiguity: when several rules fit, prefer the simplest natural one; do not "
        "guess from one example.\n"
        "- Cumulative state and boundary cases (empty list, one element, negatives, "
        "duplicates) need explicit handling.\n"
        "- Budget: checks only validate shown examples, so passing them is necessary but "
        "not evidence of generalization. Preserve checked solutions when later attempts "
        "fail, and spend budget on the attempts most likely to help.\n"
        "The improver must change too: make its selection and prompting measurably "
        "better, not just reworded. Compare trial proposals on equal task counts.\n"
        "Output each complete source between a line <file name=\"NAME\"> and a line "
        "</file>, followed by <note>one line of useful advice for the next generation</note>."
    )
    try:
        budget = api.budget()
        calls = min(2, budget.get("llm_calls", 0))
        per_trial = min(
            len(ctx["results"]),
            budget.get("trial_tasks", 0) // max(calls, 1),
        )
    except Exception:
        calls, per_trial = 1, 0

    candidates = []
    for index in range(calls):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            extra = (
                "\nExplore a distinct general strategy from the first proposal; "
                "do not reuse its main mechanism."
                if index else ""
            )
            files, note = parse(api.llm(prompt + extra, system=SYSTEM))
            if not all(name in files for name in ("solver.py", "improver.py")):
                continue
            try:
                for name in ("solver.py", "improver.py"):
                    compile(files[name], name, "exec")
            except (SyntaxError, ValueError, TypeError):
                continue
            score = None
            if per_trial and api.budget().get("trial_tasks", 0) >= per_trial:
                try:
                    score = api.trial(files["solver.py"], per_trial)["solved"] / per_trial
                except Exception:
                    pass
            candidates.append((score, files, note))
        except api.BudgetExceeded:
            break
        except Exception:
            continue

    if not candidates:
        return {"files": {}, "note": "No usable proposal; inspect parsing and budget limits."}
    tested = [item for item in candidates if item[0] is not None]
    _, files, note = max(tested, key=lambda item: item[0]) if tested else candidates[0]
    return {"files": files, "note": note}
