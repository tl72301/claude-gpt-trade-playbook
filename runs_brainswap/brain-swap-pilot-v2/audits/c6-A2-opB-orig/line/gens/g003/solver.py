"""Infer a list transformation from examples and validate candidate code."""

import ast
import re

SYSTEM = (
    "You infer compact, general Python list transformations from examples. "
    "Prioritize the simplest rule that explains every example, not memorization."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^(?:from \S+ import .*\n|import .*\n|def f\s*\()", text)
    return text[match.start():].strip() if match else text.strip()


def has_f(code):
    try:
        tree = ast.parse(code)
        return any(isinstance(node, ast.FunctionDef) and node.name == "f"
                   for node in tree.body)
    except (SyntaxError, ValueError, TypeError):
        return False


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}"
        for ex in task.get("examples", [])
    )
    prompt = (
        "Infer the intended transformation from ALL the examples below. "
        "The examples may not uniquely determine the rule: compare plausible "
        "simple rules and favor one that explains every detail without special "
        "cases or memorizing examples. Consider filtering before or after a "
        "transformation, indexing, adjacent pairs, order, duplicates, and "
        "boundary conditions. Check your chosen rule manually on every example.\n\n"
        + shown + "\n\n"
        "Return only executable Python code defining def f(xs), in a Python "
        "code block. It must return a list of ints and handle empty inputs."
    )
    best = "def f(xs):\n    return []\n"
    best_score = -1
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not has_f(code):
            prompt += "\nYour previous response did not define a valid function f. Return code only."
            continue
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            if best_score < 0:
                return code
            break
        except Exception:
            prompt += "\nThe previous code could not be checked. Return a valid, self-contained function."
            continue
        score = sum(bool(r.get("passed")) for r in report)
        if score > best_score:
            best, best_score = code, score
        failed = [r for r in report if not r.get("passed")]
        if not failed:
            return code
        feedback = "\n".join(
            f"f({r.get('input')!r}) returned {r.get('actual')!r}; "
            f"expected {r.get('expected')!r}."
            for r in failed
        )
        prompt += (
            f"\n\nCandidate {attempt + 1}:\n```python\n{code}\n```\n"
            f"It failed these shown examples:\n{feedback}\n"
            "Reconsider the underlying rule, not just these individual inputs. "
            "Return a complete corrected function."
        )
    return best
