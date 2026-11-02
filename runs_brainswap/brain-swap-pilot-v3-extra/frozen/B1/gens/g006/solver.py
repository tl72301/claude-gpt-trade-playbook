"""Example-driven Python function synthesizer."""
import re

SYSTEM = (
    "You infer precise Python list transformations from examples. "
    "Look for a simple rule that explains every example, not coincidences."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.DOTALL)
    for block in reversed(blocks):
        if re.search(r"(?m)^\s*def\s+f\s*\(", block):
            return block.strip()
    match = re.search(r"(?m)^def\s+f\s*\(", text)
    if match:
        code = text[match.start():]
        code = re.split(r"(?m)^```", code, maxsplit=1)[0]
        return code.strip()
    return text.strip()


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended general rule mapping a list of integers to a list "
        "of integers. Every example is exact:\n" + examples + "\n\n"
        "Compare plausible rules against ALL examples. Consider adjacent pairs "
        "and triples, filtering before versus after transforming, indices versus "
        "values, order, signs, parity, and output length. Avoid fitting accidental "
        "correlations: choose the simplest consistent uniform rule. Think carefully "
        "about empty inputs, repeated values, negative numbers and boundaries. "
        "Return a complete standard-library-only Python implementation defining "
        "def f(xs) in a fenced Python block. Do not hardcode examples. Keep any "
        "explanation brief."
    )
    code = "def f(xs):\n    return []"
    feedback = ""
    for _ in range(3):
        try:
            reply = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        candidate = extract(reply)
        if not re.search(r"(?m)^\s*def\s+f\s*\(", candidate):
            feedback += (
                "\nYour last response did not contain a function definition. "
                "Return executable Python defining def f(xs), in a code block."
            )
            continue
        code = candidate
        try:
            if api.budget().get("checks", 0) <= 0:
                break
            report = api.check(candidate)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            return candidate
        feedback += (
            "\n\nYour previous implementation:\n```python\n" + candidate
            + "\n```\nfailed these examples:\n"
            + "\n".join(
                f"f({r['input']!r}) returned {r['actual']!r}; "
                f"expected {r['expected']!r}"
                for r in failed
            )
            + "\nReconsider the rule and return a corrected complete function."
        )
    return code
