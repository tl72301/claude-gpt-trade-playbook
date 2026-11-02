"""Example-driven Python function solver."""

import ast
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


def valid(code):
    try:
        tree = ast.parse(code)
        return any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and node.name == "f" for node in tree.body)
    except (SyntaxError, ValueError, TypeError):
        return False


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}"
        for ex in task["examples"]
    )
    base = (
        "Infer the intended general rule for def f(xs), mapping a list of "
        "integers to a list of integers. Every example must be satisfied:\n"
        + shown
        + "\n\nWork systematically. Align each output with possible source "
        "elements or adjacent windows, including skipped elements and repeated "
        "values. Compare simple rules that explain ALL examples and output "
        "lengths and ordering. Consider filter-then-map and map-then-filter, "
        "adjacent pairs and triples, index and value conditions, parity, signs, "
        "divisibility, comparisons, absolute values, sums and differences. "
        "Consider whether outputs encode comparisons or signs. For negative "
        "values distinguish Python modulo from signed arithmetic. Check strict "
        "versus non-strict conditions, zero, and short or empty lists. Avoid "
        "memorization and prefer the simplest natural consistent rule. "
        "Identify plausible alternative rules and look for examples that "
        "distinguish them before choosing. "
        "Briefly reason, then give a complete standalone function named f "
        "in one Python code block. Use only the standard library."
    )
    prompt = base
    code = ""
    best = ""
    for attempt in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            reply = api.llm(prompt, system=SYSTEM)
            candidate = extract(reply)
            if not valid(candidate):
                prompt += (
                    "\n\nYour response did not contain a valid Python function "
                    "named f. Return the complete function in a Python code block."
                )
                continue
            code = candidate
            best = candidate
            if api.budget().get("checks", 0) <= 0:
                return candidate
            report = api.check(candidate)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r.get("passed")]
        if not failed:
            return candidate
        details = "\n".join(
            f"f({r.get('input')!r}): expected {r.get('expected')!r}, "
            f"got {r.get('actual')!r}"
            for r in failed
        )
        prompt += (
            "\n\nThe following candidate failed:\n```python\n"
            + candidate + "\n```\n" + details
            + "\nReconsider the rule from scratch, aligning every output with "
            "its source and checking all examples. Return a corrected complete "
            "function in a Python code block."
        )
    return best or code
