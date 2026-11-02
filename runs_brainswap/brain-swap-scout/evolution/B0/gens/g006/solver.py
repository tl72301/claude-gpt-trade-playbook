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
        "Infer the intended deterministic function f(xs). Input and output are "
        "lists of integers. All available examples:\n"
        f"{shown}\n\n"
        "Analyze ALL examples before choosing a rule. Compare output lengths "
        "with input length and with counts of elements satisfying conditions. "
        "An output element need not correspond to the input at the same index. "
        "Try mapping, filtering then mapping, adjacent or non-overlapping "
        "pairs, sliding windows, runs, grouping, and aggregations. Consider "
        "whether an output value comes from arithmetic on several elements, "
        "their indices, counts, or whole-list statistics. A fixed-size output "
        "can contain counts or integer indicators of several conditions.\n\n"
        "Consider different plausible operations and their compositions, "
        "including differences, sums, parity, divisibility, frequencies, "
        "ordering, comparisons with neighbors and positions, and prefix or "
        "suffix properties. Trace each proposed rule against every example, "
        "including duplicates and negative values. Distinguish strict from "
        "non-strict comparisons, overlapping from disjoint windows, and "
        "Python floor division from truncation. Prefer a simple conventional "
        "rule over unsupported special cases. Handle empty and short lists "
        "sensibly. Do not memorize examples or use task IDs.\n\n"
        "Return only a Python code block containing the complete definition "
        "of f(xs)."
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
        "\n\nDerive the rule independently. In particular, test whether "
        "outputs are produced by selecting windows or pairs before applying "
        "arithmetic, or represent multiple related counts or indicators. "
        "Do not assume the output length is determined only by input length.",
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
        + "\n\nIndependently review the algorithms, not merely their code. "
        "For alternatives that pass, identify concrete small inputs on which "
        "they disagree and reason which behavior is most consistent with the "
        "examples and a natural general rule. Check whether output length and "
        "ordering support each hypothesis. Pay particular attention to ties, "
        "boundaries, negative values, selection before transformation, and "
        "strict versus non-strict conditions. Do not replace a supported rule "
        "with a speculative complication. If none passed, use the failed "
        "checks to derive a different rule. Return only the complete best "
        "function in a Python code block."
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
