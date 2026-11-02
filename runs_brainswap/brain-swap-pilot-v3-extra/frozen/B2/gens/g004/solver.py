"""Example-driven Python function synthesis."""

import ast
import re

SYSTEM = (
    "You infer precise Python list transformations from examples. "
    "Distinguish rules that fit the examples from rules that generalize. "
    "Respect ordering, duplicates, ties, and boundary cases."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    for candidate in list(reversed(blocks)) + [text]:
        candidate = candidate.strip()
        try:
            tree = ast.parse(candidate)
            if any(isinstance(node, ast.FunctionDef) and node.name == "f"
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
        "Infer a single simple, general list transformation consistent with ALL examples:\n"
        + examples +
        "\n\nFirst analyze the examples carefully. Align each output element with possible "
        "input elements, indices, consecutive pairs or triples, windows, or runs. "
        "Output length may indicate filtering before or after computing a relation. "
        "Consider signs, parity, divisibility, comparisons, differences, counts, and "
        "indices where appropriate. Compare plausible competing rules, especially "
        "rules that agree on the examples but differ on boundaries, ordering, or ties. "
        "Do not assume every output corresponds to an adjacent input position. "
        "Choose the simplest uniform rule, not a lookup table. "
        "Then return a complete executable standard-library-only def f(xs), returning "
        "a list of ints, in a Python code block."
    )
    best = None
    feedback = ""
    for attempt in range(3):
        if attempt == 0:
            request = prompt
        elif best is None or feedback:
            request = (
                prompt + "\n\nPrevious attempt:\n" + (best or "(no valid function)")
                + "\n" + feedback +
                "\nReconsider the rule and return the complete corrected function."
            )
        else:
            request = (
                prompt + "\n\nA candidate that fits the visible examples is:\n" + best +
                "\nIndependently examine whether this candidate uses an unnecessarily "
                "specific assumption or misses a more natural general rule. Trace ALL "
                "examples, including their output lengths. Consider competing hypotheses "
                "and edge cases. Keep the candidate if it is the best-supported rule; "
                "otherwise correct it. Return the complete function in a code block."
            )
        try:
            reply = api.llm(request, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if code is None:
            feedback = "The response did not contain a syntactically valid function named f."
            continue
        try:
            if api.budget().get("checks", 0) > 0:
                report = api.check(code)
                failed = [r for r in report if not r["passed"]]
                if failed:
                    feedback = "Failed examples:\n" + "\n".join(
                        f"f({r['input']!r}): expected {r['expected']!r}, got {r['actual']!r}"
                        for r in failed
                    )
                    if best is None:
                        best = code
                    continue
        except Exception:
            if best is None:
                best = code
            break
        best = code
        feedback = ""
        if attempt >= 1:
            break
    return best or "def f(xs):\n    return []\n"
