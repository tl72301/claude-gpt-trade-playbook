"""Example-driven Python function synthesis."""

import ast
import re

SYSTEM = (
    "You infer simple, precise Python list transformations from examples. "
    "Respect ordering, duplicates, ties, and boundary cases."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    candidates = list(reversed(blocks)) + [text]
    for candidate in candidates:
        candidate = candidate.strip()
        try:
            tree = ast.parse(candidate)
            if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "f"
                   for node in tree.body):
                return candidate
        except SyntaxError:
            pass
    return None


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the simplest uniform transformation consistent with ALL examples:\n"
        + examples
        + "\n\nConsider filtering, consecutive pairs or triples, windows and runs. "
        "Check output length, ordering, duplicates and ties. Consider alternative rules "
        "and edge cases. Do not use a lookup table. Return a complete executable "
        "standard-library-only `def f(xs):` returning a list of ints, in a Python code block."
    )
    best = None
    feedback = ""
    for attempt in range(3):
        if attempt:
            request = (
                prompt + "\n\nPrevious attempt:\n" + (best or "(no valid Python function)")
                + "\n" + feedback
                + "\nReconsider the general rule and return the complete corrected function "
                "in a Python code block. Ensure that `def f(xs):` is present."
            )
        else:
            request = prompt
        try:
            reply = api.llm(request, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if code is None:
            feedback = "The response did not contain a syntactically valid function named f."
            continue
        best = code
        try:
            if api.budget().get("checks", 0) <= 0:
                return best
            report = api.check(code)
            failed = [r for r in report if not r["passed"]]
            if not failed:
                return best
            feedback = "Failed examples:\n" + "\n".join(
                f"f({r['input']!r}): expected {r['expected']!r}, got {r['actual']!r}"
                for r in failed
            )
        except Exception:
            return best
    return best or "def f(xs):\n    return []\n"
