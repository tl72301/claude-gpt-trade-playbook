"""Synthesize a list-to-list function from examples."""

import ast
import re

SYSTEM = (
    "You infer compact Python programs from examples. "
    "Generalize the generating rule rather than memorizing examples."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.DOTALL | re.I)
    candidates = list(reversed(blocks)) + [text]
    for candidate in candidates:
        candidate = candidate.strip()
        try:
            tree = ast.parse(candidate)
            if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and node.name == "f" for node in tree.body):
                return candidate
        except SyntaxError:
            pass
    # Recover a function when the response includes surrounding prose.
    match = re.search(r"(?m)^def f\s*\(", text)
    if match:
        lines = text[match.start():].splitlines()
        for end in range(len(lines), 0, -1):
            candidate = "\n".join(lines[:end]).strip()
            try:
                tree = ast.parse(candidate)
                if any(isinstance(node, ast.FunctionDef) and node.name == "f"
                       for node in tree.body):
                    return candidate
            except SyntaxError:
                continue
    return ""


def solve(task, api):
    examples = "\n".join(
        f"f({example['input']!r}) == {example['output']!r}"
        for example in task["examples"]
    )
    prompt = (
        "Infer a concise general rule for def f(xs), mapping a list of integers "
        "to a list of integers. All examples must be satisfied:\n"
        + examples
        + "\n\nConsider multiple hypotheses before coding. Outputs might be values, "
        "indices, counts, differences, or other transformations; they may arise from "
        "individual elements, neighboring pairs, runs, or filtered groups. "
        "Distinguish the order of operations: filtering before versus after grouping "
        "or transforming, and sorting versus preserving input order. Check duplicates, "
        "signs, zero, ties, endpoint handling, and strict versus inclusive comparisons. "
        "Prefer a simple consistent rule without unsupported exceptions. "
        "Handle empty and short lists. Return complete executable Python defining f "
        "in a code block, with any required imports."
    )
    best = ""
    best_status = -1
    candidate = ""
    feedback = ""

    for attempt in range(2):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            query = prompt
            if attempt:
                query += (
                    "\n\nIndependently review the candidate below. Test competing "
                    "interpretations against every example, especially operation order "
                    "and boundary cases. Retain the rule if it is best supported; "
                    "otherwise correct it. Return the complete function.\n"
                    + feedback
                    + "\nCandidate:\n```python\n" + candidate + "\n```"
                )
            candidate = extract(api.llm(query, system=SYSTEM))
        except api.BudgetExceeded:
            break

        if not candidate:
            feedback = "The previous response did not contain a usable function f."
            continue

        status = 0
        feedback = "The candidate was not checked."
        try:
            if api.budget().get("checks", 0) > 0:
                results = api.check(candidate)
                failures = [result for result in results if not result["passed"]]
                if failures:
                    status = -1
                    feedback = "The candidate fails shown examples:\n" + "\n".join(
                        f"input={result.get('input')!r}, "
                        f"expected={result.get('expected')!r}, "
                        f"actual={result.get('actual')!r}"
                        for result in failures[:5]
                    )
                else:
                    status = 1
                    feedback = "The candidate passes the shown examples."
        except api.BudgetExceeded:
            pass
        except Exception as exc:
            status = -1
            feedback = f"Checking the candidate raised {exc!r}."

        # A verified revision is preferable, but do not replace a verified program
        # with one that fails or could not be checked.
        if not best or status > best_status or (status == best_status and status >= 0):
            best, best_status = candidate, status

    return best
