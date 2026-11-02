"""Example-driven Python function synthesis."""

import ast
import re

SYSTEM = (
    "You infer the intended general rule from examples and write precise Python. "
    "Prefer simple, conventional transformations that generalize to unseen inputs."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.I)
    candidates = list(reversed(blocks)) + [text]
    for candidate in candidates:
        try:
            tree = ast.parse(candidate)
            if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and node.name == "f" for node in tree.body):
                return candidate
        except SyntaxError:
            pass
    match = re.search(r"(?m)^def f\s*\(", text)
    return text[match.start():] if match else (blocks[-1] if blocks else text)


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended list-to-list transformation from ALL examples below. "
        "Look for a compact general rule, not a lookup table. Consider filtering, "
        "mapping, positions, neighbors, ordering, duplicates, and combinations of "
        "these. Distinguish plausible competing rules using all available examples; "
        "avoid assuming a threshold or arithmetic operation without evidence. "
        "Preserve the demonstrated order and handle empty and short lists. "
        "The hidden tests may include boundary cases and negative numbers.\n\n"
        + examples
        + "\n\nReturn only a Python code block defining def f(xs). "
        "You may briefly explain the inferred rule in a code comment."
    )
    best_code = ""
    best_score = -1
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return best_code if best_score >= 0 else code
        score = sum(bool(item["passed"]) for item in report)
        if score > best_score:
            best_code, best_score = code, score
        failures = [item for item in report if not item["passed"]]
        if not failures:
            return code
        feedback = "\n".join(
            f"f({item['input']!r}): got {item['actual']!r}, "
            f"expected {item['expected']!r}"
            for item in failures
        )
        prompt += (
            "\n\nThe previous code failed these shown examples:\n"
            + feedback
            + "\nPrevious code:\n" + code
            + "\nReconsider the rule and return a corrected complete function. "
            "It must satisfy every example, not just the failures."
        )
    return best_code
