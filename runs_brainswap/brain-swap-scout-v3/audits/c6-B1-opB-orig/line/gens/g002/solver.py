"""Example-driven synthesis with optional verification and revision."""
import ast
import re

SYSTEM = (
    "You synthesize small Python functions from examples. Infer the simplest "
    "general rule, not a lookup table. Be careful about ambiguous examples."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    candidates = list(reversed(blocks)) + [text]
    for code in candidates:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        if any(isinstance(n, ast.FunctionDef) and n.name == "f" for n in tree.body):
            return code
    return ""


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Write Python source defining def f(xs), taking a list of integers and "
        "returning a list of integers. Infer one general rule consistent with "
        "ALL examples:\n" + shown + "\n\n"
        "Before coding, compare plausible rules rather than settling on the "
        "first match. Pay attention to output order, duplicates, zero and "
        "negative values, strict versus inclusive thresholds, and whether "
        "outputs are values, indices, counts, or transformed values. Consider "
        "filters followed by transformations, adjacent pairs or windows, "
        "positions in the original versus filtered list, frequencies, and "
        "global aggregates. Prefer a simple rule that explains every example "
        "without arbitrary constants or special cases. Handle empty inputs and "
        "short lists where appropriate. Return only executable code in one "
        "Python code block."
    )
    best = ""
    best_failures = None
    feedback = ""
    for attempt in range(3):
        if api.budget().get("llm_calls", 0) <= 0:
            break
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not code:
            feedback += "\nYour last response did not define a valid function f. Return complete Python code."
            continue

        failures = None
        if api.budget().get("checks", 0) > 0:
            try:
                report = api.check(code)
                failures = [r for r in report if not r["passed"]]
            except api.BudgetExceeded:
                pass
        if failures is None:
            if not best:
                best = code
            break
        if best_failures is None or len(failures) < best_failures:
            best, best_failures = code, len(failures)
        if failures:
            details = "\n".join(
                f"f({r['input']!r}): got {r['actual']!r}, expected {r['expected']!r}"
                for r in failures
            )
            feedback = (
                "\n\nThe following candidate failed supplied examples:\n```python\n"
                + code + "\n```\n" + details
                + "\nReconsider the whole rule and return corrected complete code."
            )
        else:
            if attempt > 0 or api.budget().get("llm_calls", 0) <= 0:
                break
            feedback = (
                "\n\nThis candidate passes the examples, but they may not uniquely "
                "identify the rule:\n```python\n" + code + "\n```\n"
                "Independently reconsider alternative explanations, especially "
                "boundary cases and whether outputs represent values or positions. "
                "Change the candidate only if another simple rule explains the "
                "examples more naturally. Return complete code."
            )
            # Prefer a verified revision if it also passes.
            best_failures = 1
    return best or "def f(xs):\n    return []\n"
