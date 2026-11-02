"""Infer a list transformation from examples and validate the generated code."""

import ast
import re

SYSTEM = (
    "You are an expert at inferring small deterministic Python list transformations. "
    "Use every example and prefer a simple, general rule over memorization."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    code = blocks[-1] if blocks else text
    try:
        tree = ast.parse(code)
        names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
        if "f" not in names and names:
            code += "\n\nf = " + names[-1] + "\n"
    except SyntaxError:
        pass
    return code


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}"
        for ex in task["examples"]
    )
    prompt = (
        "Infer the intended rule and write Python code defining def f(xs), "
        "returning a list of integers.\n\n"
        + examples
        + "\n\n"
        "First reason carefully about ALL examples. Determine exactly which input "
        "elements or positions produce outputs, their order, and the output length. "
        "Consider filtering by value, parity, sign, divisibility, index, neighbors, "
        "and combinations of these, as well as transformations, adjacent pairs, "
        "counts and ordering. Check boundary cases and distinguish similar rules "
        "(such as > versus >=, odd values versus odd indices). Avoid assumptions "
        "that fit only a subset of examples. Prefer the simplest rule that explains "
        "every output, including empty outputs and repeated values. Do not hardcode "
        "the examples. Briefly state the inferred rule, then return the complete "
        "function in a Python code block."
    )
    best_code = "def f(xs):\n    return []\n"
    best_score = -1
    for attempt in range(3):
        try:
            response = api.llm(prompt, system=SYSTEM)
            code = extract(response)
            results = api.check(code)
        except api.BudgetExceeded:
            break
        score = sum(bool(r.get("passed")) for r in results)
        if score > best_score:
            best_score, best_code = score, code
        failures = [r for r in results if not r.get("passed")]
        if not failures:
            return code
        feedback = "\n".join(
            f"f({r.get('input')!r}): got {r.get('actual')!r}, "
            f"expected {r.get('expected')!r}"
            for r in failures
        )
        prompt += (
            f"\n\nAttempt {attempt + 1}:\n{code}\n"
            f"Failed checks:\n{feedback}\n"
            "Reconsider the selection rule, output length, order and transformation "
            "against all examples. Return a corrected complete function."
        )
    return best_code
