"""Improve the solver and its improvement procedure using development feedback."""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver that writes Python functions "
    "from examples and an improvement procedure that rewrites the agent."
)

BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    remaining = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    note = re.search(r"<note>(.*?)</note>", remaining, re.DOTALL)
    return files, note.group(1).strip() if note else ""


def classify(item):
    failure = str(item.get("failure", "")).lower()
    if "function" in failure and any(x in failure for x in ("no ", "define", "usable")):
        return "no_f"
    if any(x in failure for x in ("unparsable", "syntax", "exception", "error")):
        return "runtime_or_parse"
    if any(
        len(ex.get("input", [])) != len(ex.get("output", []))
        for ex in item.get("examples", [])
    ):
        return "wrong_rule_wrong_length"
    return "wrong_rule"


def pattern_counts(results):
    counts = {}
    for item in results:
        if not item.get("passed"):
            key = classify(item)
            counts[key] = counts.get(key, 0) + 1
    return counts


def describe(results):
    lines = []
    for item in results:
        if item.get("passed"):
            lines.append(f"- {item.get('id')}: solved")
            continue
        lines.append(
            f"- {item.get('id')}: FAILED ({item.get('failure')}) "
            f"[{classify(item)}]"
        )
        for ex in item.get("examples", []):
            lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    improver = api.source("improver.py")
    results = ctx["results"]
    counts = pattern_counts(results)
    dominant = max(counts, key=counts.get) if counts else "none"
    guidance = {
        "wrong_rule_wrong_length": (
            "Prioritize inferring selection, ordering, output length and boundary "
            "conditions. Compare plausible rules against every example."
        ),
        "wrong_rule": (
            "Prioritize distinguishing plausible transformations and testing "
            "boundary conditions against every example."
        ),
        "runtime_or_parse": (
            "Prioritize robust extraction, valid Python, and feedback-driven repair."
        ),
        "no_f": "Ensure returned code defines a callable named f.",
    }.get(dominant, "Preserve correct behavior and improve generalization.")
    prompt = (
        f"Generation {ctx['generation']}: "
        f"{sum(bool(r.get('passed')) for r in results)}/{len(results)} solved.\n"
        f"Failure patterns: {counts}; dominant: {dominant}.\n"
        f"Guidance: {guidance}\n"
        f"Memory: {ctx.get('memory') or '(none)'}\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{improver}\n=== END FILE ===\n\n"
        f"Results:\n{describe(results)}\n\n"
        "Rewrite BOTH files. Preserve their contracts and keep api.check with "
        "feedback in the solver. Improve hidden-test generalization, not just "
        "example fitting. Make the improver adapt to observed failures and use "
        "available trials when useful. Return each full source between lines "
        '<file name="NAME"> and </file>, followed by '
        "<note>dominant pattern and next-step guidance</note>."
    )
    best = None
    best_score = -1
    for _ in range(2):
        try:
            text = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(text)
        if not files.get("solver.py") or not files.get("improver.py"):
            continue
        if files["improver.py"] == improver:
            continue
        score = 0
        candidate = files["solver.py"]
        score += int("api.check" in candidate)
        score += int("def f" in candidate)
        try:
            budget = api.budget()
            n = min(8, budget.get("trial_tasks", 0))
            if n:
                trial = api.trial(candidate, n)
                score += 10 * trial["solved"]
        except api.BudgetExceeded:
            pass
        if score > best_score:
            best_score = score
            best = (files, note)
    if best is None:
        return {"files": {}, "note": f"{dominant}: no usable proposal"}
    return {"files": best[0], "note": best[1]}
