"""Example-based Python function synthesizer."""

import re

SYSTEM = (
    "You infer compact, general Python transformations from examples. "
    "Distinguish what the examples prove from what they merely suggest."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def solve(task, api):
    examples = "\n".join(
        f"f({example['input']!r}) == {example['output']!r}"
        for example in task["examples"]
    )
    prompt = (
        "Infer the intended rule for def f(xs), returning a list of ints.\n"
        "Examples:\n" + examples + "\n\n"
        "Consider multiple simple rules before choosing one. Check every example "
        "element by element, including output order and duplicates. Consider "
        "filters, arithmetic transformations, indices, neighbor relationships, "
        "sorting, and combinations of these. Do not assume a boundary case "
        "such as zero, negative numbers, ties, or empty input without evidence. "
        "Prefer a simple rule that explains all observations rather than an "
        "example-specific or arbitrary condition. Handle short and empty lists. "
        "Return only the complete function in a Python code block."
    )
    best = ""
    feedback = ""
    while True:
        budget = api.budget()
        if budget.get("llm_calls", 0) <= 0:
            break
        try:
            answer = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(answer)
        if not code:
            break
        best = code
        if api.budget().get("checks", 0) <= 0:
            break
        try:
            results = api.check(code)
        except api.BudgetExceeded:
            break
        failures = [result for result in results if not result["passed"]]
        if not failures:
            break
        details = "\n".join(
            f"f({result['input']!r}): expected {result['expected']!r}, "
            f"got {result['actual']!r}"
            for result in failures
        )
        feedback = (
            "\n\nYour previous function failed these examples:\n" + details
            + "\nPrevious code:\n" + code
            + "\nReconsider the rule and return a corrected complete function."
        )
    return best or "def f(xs):\n    return []\n"
