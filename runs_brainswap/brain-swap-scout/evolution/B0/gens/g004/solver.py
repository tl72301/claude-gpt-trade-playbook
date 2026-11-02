"""Infer and verify a general list transformation from examples."""

import re

SYSTEM = (
    "You are an expert at inferring small deterministic Python programs from "
    "input/output examples. Infer the intended general algorithm rather than "
    "memorizing cases. Use only the Python standard library."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = task.get("examples", [])
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in examples
    )
    prompt = (
        "Infer the intended deterministic function f(xs). Both input and output "
        "are lists of integers. These are all the available examples:\n"
        f"{shown}\n\n"
        "First analyze output shape and ordering. For each output, determine "
        "which inputs or positions could have produced it. Then compare several "
        "genuinely different simple algorithms against ALL examples, including "
        "negative numbers and duplicates. Do not infer a rule from just one "
        "example or assume that outputs correspond to inputs at the same index.\n\n"
        "Consider compositions, not just single operations: select elements or "
        "positions, then transform them; group or sort, then aggregate; or compute "
        "a statistic and return it in a list. Candidates include comparisons with "
        "neighbors, positions, prefix/suffix or whole-list statistics, counts and "
        "frequencies, parity and modular arithmetic, differences and sums, ranks, "
        "runs, and sliding windows. A short output may represent selected items, "
        "aggregates, or window results. A constant-length output may encode "
        "several related statistics. Python's modulo and floor division for "
        "negative numbers deserve special attention.\n\n"
        "Check each proposed rule by manually tracing every output in every "
        "example. Where several rules fit, prefer the simplest conventional "
        "algorithm, and examine small, empty, duplicate-heavy, and negative "
        "inputs to expose unsupported assumptions. Do not use task IDs, "
        "memorize examples, or add arbitrary special cases. Implement sensible "
        "behavior for empty and short lists. Return only a Python code block "
        "containing the complete definition of f(xs)."
    )
    candidates = []
    failures = []

    def check(code):
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return None, ""
        failed = [r for r in report if not r.get("passed")]
        feedback = "\n".join(
            f"f({r.get('input')!r}): expected {r.get('expected')!r}, "
            f"got {r.get('actual')!r}"
            for r in failed
        )
        return not failed, feedback

    for extra in (
        "",
        "\n\nIndependently derive the rule from the examples. Explicitly "
        "consider competing explanations for the output length, selected "
        "positions, and arithmetic before committing to one.",
    ):
        try:
            code = extract(api.llm(prompt + extra, system=SYSTEM))
        except api.BudgetExceeded:
            break
        passed, feedback = check(code)
        if passed is None:
            if not candidates:
                candidates.append(code)
            break
        if passed:
            candidates.append(code)
        else:
            failures.append((code, feedback))

    if not candidates and not failures:
        return ""

    choices = "\n\n".join(
        f"Candidate {i + 1}:\n```python\n{code}\n```"
        for i, code in enumerate(candidates)
    )
    failed_text = "\n\n".join(
        f"Rejected candidate:\n```python\n{code}\n```\n"
        f"Failed checks:\n{feedback}"
        for code, feedback in failures
    )
    request = (
        prompt + "\n\n" + choices + "\n\n" + failed_text
        + "\n\nIndependently review the underlying algorithms. For alternatives "
        "that pass, identify concrete small inputs on which they disagree and "
        "reason which behavior is most consistent with the examples and a "
        "natural general rule. Pay particular attention to ties, boundaries, "
        "negative values, ordering, and whether a condition is strict. "
        "Do not replace a supported rule with a speculative complication. "
        "If none passed, use the failed checks to derive a different rule. "
        "Return only the complete best function in a Python code block."
    )
    try:
        revised = extract(api.llm(request, system=SYSTEM))
    except api.BudgetExceeded:
        return candidates[0] if candidates else failures[-1][0]

    passed, _ = check(revised)
    if passed:
        return revised
    if candidates:
        return candidates[0]
    return revised
