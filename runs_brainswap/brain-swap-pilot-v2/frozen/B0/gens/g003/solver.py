"""Infer a list transformation from examples, checking candidate implementations."""

import re

SYSTEM = (
    "You are an expert at inferring small deterministic Python programs from "
    "input/output examples. Prefer simple, general rules over memorization. "
    "Check every proposed rule against every example before coding."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    base = (
        "Infer the intended list transformation from all these examples:\n" + shown +
        "\n\nFirst work out several distinct plausible rules and explicitly test "
        "each against every example. Look especially at output length and order, "
        "positions versus values, adjacent pairs and windows, runs, frequencies, "
        "ranks, parity, arithmetic, filtering and grouping. Consider whether the "
        "output is a scalar statistic wrapped in a list or one result per group. "
        "Distinguish similar rules using the examples rather than assuming the "
        "first matching pattern. Avoid special cases fitted to individual examples. "
        "Consider duplicates, negative values, ties, empty and short inputs, and "
        "partial groups. Select the simplest general rule supported by the evidence. "
        "Implement `def f(xs):` using only the Python standard library. "
        "Return only the complete code in a Python fenced block."
    )
    prompt = base
    best = ""
    best_failures = None
    for attempt in range(3):
        try:
            candidate = extract(api.llm(prompt, system=SYSTEM))
        except api.BudgetExceeded:
            break
        if not candidate:
            continue
        try:
            report = api.check(candidate)
        except api.BudgetExceeded:
            if not best:
                best = candidate
            break
        failed = [r for r in report if not r["passed"]]
        if best_failures is None or len(failed) < best_failures:
            best, best_failures = candidate, len(failed)
        if not failed:
            if attempt or best_failures == 0:
                # Use a remaining call to scrutinize generalization, not merely
                # consistency with the visible examples.
                try:
                    review = api.llm(
                        base + "\n\nA candidate consistent with the examples is:\n"
                        "```python\n" + candidate + "\n```\n"
                        "Independently scrutinize the rule. Identify any simpler "
                        "or more natural competing rule that also explains ALL "
                        "examples, especially for boundary cases, duplicates and "
                        "ordering. Change the implementation only if the evidence "
                        "strongly favors the alternative or reveals a bug. Return "
                        "the complete best function in a Python fenced block.",
                        system=SYSTEM,
                    )
                    revised = extract(review)
                    if revised and revised != candidate:
                        try:
                            checked = api.check(revised)
                            if all(r["passed"] for r in checked):
                                best = revised
                        except api.BudgetExceeded:
                            pass
                except api.BudgetExceeded:
                    pass
            return best
        details = "\n".join(
            f"f({r['input']!r}): got {r['actual']!r}, expected {r['expected']!r}"
            for r in failed
        )
        prompt = (
            base + "\n\nThe previous implementation was:\n```python\n" +
            candidate + "\n```\nIt failed these examples:\n" + details +
            "\nReconsider the underlying rule rather than patching individual "
            "examples. Return a corrected complete function consistent with all "
            "examples."
        )
    return best
