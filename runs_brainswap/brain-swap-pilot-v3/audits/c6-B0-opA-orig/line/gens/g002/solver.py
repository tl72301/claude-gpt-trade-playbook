import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Infer the simplest general rule that explains ALL examples, not a lookup table."
)
ATTEMPTS = 4
HINTS = [
    "Consider the output length relative to the input length (same, n-1, n-k, fewer via filtering).",
    "Common building blocks: prefix sums/running min/max/counts, adjacent pair ops, windows, "
    "filtering by predicate, sorting, index-dependent ops (i*x, parity of index), mod arithmetic.",
    "Prefer the simplest rule that fits every example; avoid hard-coding example values.",
    "Handle edge cases such as empty or length-1 lists without raising.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def score(report):
    return sum(1 for r in report if r["passed"])


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {h}\n" for h in HINTS)
        + "First briefly analyze the examples (lengths, differences, sums) in plain text, "
        "then give the final code in one ```python block."
    )
    prompt = base
    best, best_score = "", -1
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM, max_tokens=1500)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            return best or code
        except Exception:
            report = []
        s = score(report) if report else 0
        if s > best_score:
            best, best_score = code, s
        failed = [r for r in report if not r["passed"]]
        if report and not failed:
            return code
        if not report:
            continue
        lines = "\n".join(
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:3]
        )
        prompt = (
            base + "\n\nYour previous code:\n```python\n" + code + "\n```\n"
            "It failed these examples:\n" + lines +
            "\nRe-derive the rule from all examples (do not just patch), and fix it."
        )
    return best
