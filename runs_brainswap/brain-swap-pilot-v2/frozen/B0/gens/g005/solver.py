"""Infer a list transformation from examples, checking candidate implementations."""

import re

SYSTEM = (
    "You infer small deterministic Python programs from input/output examples. "
    "Favor natural, general algorithms, not rules fitted to individual examples."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    base = (
        "Infer the intended Python list transformation from these examples:\n" + shown +
        "\n\nCompare several genuinely different rules and test each against ALL "
        "examples. Look for standard operations applied in sequence, not just a "
        "single operation: filtering then grouping, grouping then arithmetic, "
        "mapping then filtering, or differences between selected elements. "
        "Consider adjacent and non-overlapping pairs, triples and larger windows, "
        "sliding windows, strides and offsets, runs, sorted values, frequency "
        "counts, indices, parity, signs, ranks and modular arithmetic. A short "
        "output may be a filtered sequence, group results, or scalar statistics. "
        "Pay attention to output ordering, zeros, duplicates and incomplete groups. "
        "Prefer a concise conventional rule that explains every example over "
        "arbitrary thresholds or exceptions. Do not memorize the examples. "
        "Implement def f(xs) using only the Python standard library. "
        "Return only complete code in a Python fenced block."
    )
    best = ""
    best_failures = None
    prompt = base

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

        if failed:
            details = "\n".join(
                f"f({r['input']!r}): got {r['actual']!r}, expected {r['expected']!r}"
                for r in failed
            )
            prompt = (
                base + "\n\nThe previous implementation was:\n```python\n" +
                candidate + "\n```\nIt failed these examples:\n" + details +
                "\nRethink the underlying operations and their order rather "
                "than patching the examples. Return a complete corrected function."
            )
            continue

        # Ask for an independent solution without exposing the first candidate:
        # a review anchored on the first rule often repeats its assumptions.
        try:
            alternative = extract(api.llm(
                base + "\n\nIndependently derive the rule from scratch. Explicitly "
                "consider compositions of common list operations and choose the "
                "most natural rule supported by all examples.",
                system=SYSTEM,
            ))
            if not alternative or alternative == candidate:
                return best
            alt_report = api.check(alternative)
            if not all(r["passed"] for r in alt_report):
                return best
            # Both fit visible data. Compare their implied rules rather than
            # selecting a different implementation merely because it also fits.
            decision = extract(api.llm(
                base + "\n\nTwo independently proposed implementations both pass "
                "the examples:\nCandidate A:\n```python\n" + candidate +
                "\n```\nCandidate B:\n```python\n" + alternative +
                "\n```\nCompare the actual transformations, including their "
                "behavior on short inputs, ties and incomplete groups. Which is "
                "the simpler, more conventional rule best supported by all the "
                "examples? Avoid choosing an arbitrary special case. Return the "
                "complete best function in a Python fenced block.",
                system=SYSTEM,
            ))
            if decision:
                try:
                    if all(r["passed"] for r in api.check(decision)):
                        best = decision
                except api.BudgetExceeded:
                    pass
        except api.BudgetExceeded:
            pass
        return best
    return best
