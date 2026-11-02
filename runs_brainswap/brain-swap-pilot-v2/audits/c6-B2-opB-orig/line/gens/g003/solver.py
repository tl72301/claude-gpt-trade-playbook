"""Synthesize a list-to-list function from input/output examples."""

import ast
import re

SYSTEM = (
    "You infer general Python list transformations from input/output examples. "
    "Choose a compact rule that explains every example and generalizes to "
    "unseen inputs. Be precise about ordering, duplicates, and boundaries."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1].strip() if blocks else text.strip()


def valid(code):
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, TypeError):
        return False
    return any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name == "f" for node in tree.body)


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}"
        for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation and write Python code defining "
        "`def f(xs):` returning a list of ints.\n\n"
        f"{shown}\n\n"
        "First reason carefully about several competing rules, then return only "
        "the final code in a Python fenced block. Explain all examples, including "
        "empty outputs and their lengths. Do not assume outputs are input values "
        "or indices: they may be differences, counts, remainders, or other "
        "derived quantities. Consider elementwise filters, adjacent pairs or "
        "triples, runs, and relationships between non-adjacent elements. Check "
        "output ordering and multiplicity, strict versus non-strict comparisons, "
        "negative numbers, ties, and endpoint behavior. Distinguish hypotheses "
        "using all available examples; prefer a simple, uniform rule rather than "
        "arbitrary constants or special cases. Handle empty and short inputs."
    )
    best = ""
    best_passed = -1
    feedback = ""

    while api.budget().get("llm_calls", 0) > 0:
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not valid(code):
            feedback = (
                "\n\nThe previous response was not valid Python defining f. "
                "Return a complete, syntactically valid function."
            )
            continue

        if api.budget().get("checks", 0) <= 0:
            return best if best_passed >= 0 else code
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return best if best_passed >= 0 else code

        passed = sum(bool(r.get("passed")) for r in report)
        if passed > best_passed:
            best, best_passed = code, passed
        failures = [r for r in report if not r.get("passed")]
        if not failures:
            return code

        details = "\n".join(
            f"f({r.get('input')!r}): expected {r.get('expected')!r}, "
            f"got {r.get('actual')!r}"
            for r in failures
        )
        feedback = (
            "\n\nThe following candidate failed the displayed examples:\n"
            f"```python\n{code}\n```\n{details}\n"
            "Reconsider the underlying rule, including derived outputs and "
            "relationships between elements. Return a corrected complete "
            "function, without special-casing examples."
        )

    return best
