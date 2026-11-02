"""Improve the solver and the improvement procedure using development feedback."""

import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from examples. "
    "Optimize hidden-test generalization, not memorization of development tasks."
)
BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'
REQUIRED = ("solver.py", "improver.py")


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


def _budget(api):
    try:
        return api.budget() or {}
    except Exception:
        return {}


def _valid_files(files):
    if not all(name in files for name in REQUIRED):
        return False
    try:
        for name in REQUIRED:
            compile(files[name], name, "exec")
    except (SyntaxError, ValueError, TypeError):
        return False
    return "def f(" in files["solver.py"]


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
        "- Constant or sentinel outputs (all -1, all [], wrong length): the solver is "
        "defaulting or the rule is not computed from xs. Require an actual rule.\n"
        "- Invalid code (no def f, syntax errors): validate structure before spending checks.\n"
        "- Shown examples fit but hidden scores are low: the rule overfits. Prefer rules "
        "whose mechanism explains every example; hand-trace several examples first.\n"
        "- Index/value confusion and off-by-one errors: the solver prompt should require "
        "naming the index or value used for each output element.\n"
        "- Ambiguity: when several rules fit, prefer the simplest natural one.\n"
        "- Boundary cases (empty list, one element, negatives, duplicates) need explicit handling.\n"
        "- Budget: checks only validate shown examples. Keep a checked solution rather than "
        "replacing it with an unchecked rewrite.\n"
        "The improver must change too: make its selection and prompting measurably better, "
        "not just reworded. Candidates are compared against the current solver on equal "
        "task counts.\n"
        "Output each complete source between a line <file name=\"NAME\"> and a line "
        "</file>, followed by <note>one line of useful advice for the next generation</note>."
    )

    budget = _budget(api)
    n_tasks = len(ctx["results"])
    calls = min(2, int(budget.get("llm_calls", 0) or 0))
    trial_tasks = int(budget.get("trial_tasks", 0) or 0)
    # One trial for the incumbent plus one per candidate, all on the same task count.
    per_trial = min(n_tasks, trial_tasks // (calls + 1)) if calls else 0

    baseline = None
    if per_trial:
        try:
            baseline = api.trial(solver, per_trial)["solved"] / per_trial
        except Exception:
            baseline = None

    candidates = []
    for index in range(calls):
        if _budget(api).get("llm_calls", 0) <= 0:
            break
        extra = (
            "\nExplore a distinct general strategy from the first proposal; "
            "do not reuse its main mechanism."
            if index else ""
        )
        try:
            files, note = parse(api.llm(prompt + extra, system=SYSTEM))
        except api.BudgetExceeded:
            break
        except Exception:
            continue
        if not _valid_files(files):
            continue

        score = None
        if baseline is not None and _budget(api).get("trial_tasks", 0) >= per_trial:
            try:
                score = api.trial(files["solver.py"], per_trial)["solved"] / per_trial
            except api.BudgetExceeded:
                break
            except Exception:
                score = None
        candidates.append((score, files, note))

    if not candidates:
        return {"files": {}, "note": "No usable proposal; inspect parsing and budget limits."}

    if baseline is not None:
        # Accept only candidates that beat the incumbent on the same task count.
        # Ties go to the shorter solver, which is the simpler proposal.
        tested = [item for item in candidates if item[0] is not None and item[0] > baseline]
        if not tested:
            return {
                "files": {},
                "note": "No proposal beat the incumbent on equal trial tasks; keep current solver.",
            }
        _, files, note = max(
            tested, key=lambda item: (item[0], -len(item[1]["solver.py"]))
        )
        return {"files": files, "note": note}

    # No trial budget: fall back to the first structurally valid proposal.
    _, files, note = candidates[0]
    return {"files": files, "note": note}
