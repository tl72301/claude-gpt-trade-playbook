"""Infer a general list transformation from examples."""

import re

SYSTEM = (
    "You infer small, general Python functions from input/output examples. "
    "Use only the Python standard library."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1]
    match = re.search(r"(?m)^(?:from |import |def f\()", text)
    return text[match.start():] if match else text


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended rule for def f(xs), returning a list of integers.\n"
        "Examples:\n" + examples + "\n\n"
        "First reason privately about several plausible rules, then return only "
        "the Python code in one fenced block. Prefer a simple, consistent "
        "composition over a special case or a memorized table. Examine which "
        "inputs are selected, whether outputs preserve their order and "
        "duplicates, and whether output values derive from values, original "
        "indices, filtered indices, neighbors, or differences. Consider "
        "filtering before or after mapping, parity, signs, divisibility, "
        "thresholds and boundary conditions. Distinguish rules that coincide "
        "on the examples as carefully as possible. Handle empty lists, zero, "
        "negative integers and duplicates naturally. Verify every example "
        "against the proposed rule. Do not mutate the input."
    )
    code = ""
    best = ""
    best_passed = -1
    for attempt in range(3):
        if api.budget().get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        candidate = extract(reply).strip()
        if not candidate:
            continue
        code = candidate
        if api.budget().get("checks", 0) <= 0:
            return best if best else code
        try:
            report = api.check(candidate)
        except api.BudgetExceeded:
            return best if best else code
        passed = sum(bool(r["passed"]) for r in report)
        if passed > best_passed:
            best, best_passed = candidate, passed
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return candidate
        feedback = "\n".join(
            f"f({r['input']!r}): expected {r['expected']!r}, got {r['actual']!r}"
            for r in failed[:6]
        )
        prompt += (
            "\n\nThe following candidate failed the shown examples:\n```python\n"
            + candidate + "\n```\n" + feedback
            + "\nReconsider the underlying rule, not just these individual "
            "cases. Return a complete corrected function in one Python block."
        )
    return best if best else code
