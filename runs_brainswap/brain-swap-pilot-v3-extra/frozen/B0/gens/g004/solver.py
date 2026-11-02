"""Example-driven Python function solver."""

import re

SYSTEM = (
    "You infer simple list transformations from examples. Be precise about "
    "indices, filtering, order, duplicates, negative numbers, and empty inputs."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1]
    match = re.search(r"(?m)^def f\s*\(", text)
    return text[match.start():] if match else text


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}"
        for ex in task["examples"]
    )
    prompt = (
        "Infer the intended general rule for def f(xs), mapping a list of "
        "integers to a list of integers. Every example must be satisfied:\n"
        + shown
        + "\n\nWork systematically. Align each output with its possible source "
        "element or adjacent window, including skipped elements. Compare several "
        "simple candidate rules that explain ALL examples, including output length "
        "and ordering. Consider pipelines: filter elements or windows, then map "
        "them; or map first, then filter. Consider adjacent pairs and triples, "
        "index versus value conditions, parity, signs, divisibility, comparisons, "
        "absolute values, arithmetic with small constants, sums and differences. "
        "For negative values distinguish Python modulo from signed arithmetic. "
        "Check strict versus non-strict conditions and whether zero is included. "
        "Do not assume that an element was excluded merely because its mapped "
        "value equals another output. Avoid rules that merely memorize examples. "
        "Among consistent rules prefer the simplest natural transformation and "
        "explicitly consider plausible alternatives, especially for boundaries "
        "and short or empty lists.\n"
        "Briefly reason through the examples, then give the complete standalone "
        "function in a single Python code block. Use only the standard library."
    )
    code = ""
    for attempt in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            reply = api.llm(prompt, system=SYSTEM)
            code = extract(reply)
            if api.budget().get("checks", 0) <= 0:
                return code
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r.get("passed")]
        if not failed:
            return code
        details = "\n".join(
            f"f({r.get('input')!r}): expected {r.get('expected')!r}, "
            f"got {r.get('actual')!r}"
            for r in failed
        )
        prompt += (
            "\n\nThe following candidate failed:\n```python\n"
            + code + "\n```\n" + details
            + "\nReconsider the rule from scratch, aligning every output with "
            "its source and checking all examples. Return a corrected complete "
            "function in a Python code block."
        )
    return code
