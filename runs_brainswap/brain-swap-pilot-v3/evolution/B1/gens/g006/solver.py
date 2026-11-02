"""Example-driven solver."""
import ast
import re

SYSTEM = (
    "You infer integer-list transformations from examples. Seek a compact, "
    "general rule and verify it against every example. Distinguish rules that "
    "agree on the examples but behave differently on unseen inputs."
)


def extract(text):
    blocks = re.findall(
        r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE
    )
    candidates = list(reversed(blocks))
    match = re.search(r"(?m)^(?:def f\(|import |from )", text)
    if match:
        candidates.append(text[match.start():])
    candidates.append(text)
    for candidate in candidates:
        try:
            tree = ast.parse(candidate)
        except SyntaxError:
            continue
        if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name == "f" for node in tree.body):
            return candidate
    return ""


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation:\n" + shown +
        "\n\nThe input and output are lists of integers. Analyze all examples "
        "before coding. Identify which input elements or positions contribute "
        "to each output, including omitted elements and output order. Consider "
        "pipelines: filtering before or after mapping, consecutive elements in "
        "the original versus filtered list, runs and their lengths, neighboring "
        "pairs or windows, and index-dependent operations. Consider arithmetic, "
        "sign, parity and remainder rules, including negatives and duplicates. "
        "Compare plausible rules that fit ALL examples; prefer the simplest "
        "compositional rule, not an arbitrary condition fitted to observed values. "
        "Pay attention to equality and boundary cases, and consider empty and "
        "short lists. Briefly explain the competing interpretations and verify "
        "your chosen rule on every example. Finish with a Python code block "
        "defining def f(xs), using only the standard library."
    )
    code = ""
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        candidate = extract(reply)
        if not candidate:
            prompt += (
                "\nYour previous response did not contain valid Python defining "
                "a top-level function f. Return a complete implementation in a "
                "Python code block."
            )
            continue
        code = candidate
        try:
            if api.budget().get("checks", 0) <= 0:
                break
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            break
        prompt += (
            "\n\nYour previous implementation:\n```python\n" + code + "\n```\n"
            "It failed these examples:\n"
            + "\n".join(
                f"f({r['input']!r}) produced {r['actual']!r}; "
                f"expected {r['expected']!r}" for r in failed
            )
            + "\nReconsider the complete pipeline and check ALL examples, "
            "rather than patching individual cases. Return a complete corrected "
            "function in a final Python code block."
        )
    return code
