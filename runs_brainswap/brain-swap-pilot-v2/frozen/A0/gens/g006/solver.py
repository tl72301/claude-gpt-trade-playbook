"""Solver, revised in generation 3.

CONTRACT (enforced by the harness)
  solve(task, api) -> str      Python source defining def f(xs) -> list[int].
  task: {"id", "examples": [{"input": [...], "output": [...]}], "signature"}
  api.llm(prompt=None, *, messages=None, system=None, max_tokens=None) -> str
  api.check(code) -> [{"passed", "input", "expected", "actual"}]   (shown examples only)
  api.budget() -> remaining {"llm_calls", "output_tokens", "checks"}
  api.BudgetExceeded is raised when the budget is spent.
  Standard library only. No file, network or process access.
"""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "Find ONE general rule that explains every example, including the ones with "
    "unusual values. Do not hard-code outputs for the shown inputs. Output only code."
)
ATTEMPTS = 4
FALLBACK = "def f(xs):\n    return list(xs)\n"
HINTS = [
    "The rule may depend on position, neighbours, prefix or suffix, running state, or counts.",
    "Output length may differ from input length; check it against every example.",
    "Handle empty lists, single elements, zeros and negative numbers.",
    "Prefer the simplest rule that fits all examples; do not special-case individual examples.",
]


def extract(text):
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.DOTALL)
    for block in reversed(blocks):
        if re.search(r"def\s+f\s*\(", block):
            return block
    # Unterminated or unfenced code: take everything from the definition onward.
    match = re.search(r"(def\s+f\s*\(.*)", text, re.DOTALL)
    if match:
        return match.group(1).split("```")[0]
    return ""


def has_f(code):
    return bool(re.search(r"def\s+f\s*\(", code))


def solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below. The function must implement a general "
        "rule, because it will also be tested on new inputs.\n\n" + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return only the code in one ```python block, defining def f(xs)."
    )
    history = ""
    best_code, best_score = "", -1
    for attempt in range(ATTEMPTS):
        try:
            reply = api.llm(base + history, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(reply)
        if not has_f(code):
            history += (
                "\n\nYour last reply did not define a function named f. Reply with the "
                "complete code in one ```python block that defines `def f(xs):`."
            )
            continue
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            break
        except Exception:
            return code
        failed = [r for r in report if not r["passed"]]
        score = len(report) - len(failed)
        if score > best_score:
            best_code, best_score = code, score
        if not failed:
            return code
        lines = [
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
            for r in failed[:3]
        ]
        history += (
            f"\n\nAttempt {attempt + 1} was wrong on {len(failed)} example(s):\n"
            + "\n".join(lines)
            + "\nThe code you wrote was:\n```python\n" + code + "\n```\n"
            + "Find the single general rule that fits ALL examples and return the full "
            "corrected code in one ```python block defining def f(xs)."
        )
    return best_code or FALLBACK
