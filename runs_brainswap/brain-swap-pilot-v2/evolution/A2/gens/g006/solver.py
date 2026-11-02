"""Solver, revised in generation 3.

CONTRACT (enforced by the harness)
  solve(task, api) -> str      Python source defining def f(xs) -> list[int].
  task: {"id", "examples": [{"input": [...], "output": [...]}], "signature"}
  api.llm(prompt=None, *, messages=None, system=None, max_tokens=None) -> str
  api.check(code) -> [{"passed", "input", "expected", "actual"}]   (shown examples only)
  api.budget() -> remaining {"llm_calls", "output_tokens", "checks"}
  api.BudgetExceeded is raised when the budget is spent.
  Standard library only. No file, network or process access.

Changes in gen 3: the returned code is always a def f (fallback otherwise),
the best-scoring candidate is kept instead of the last one, extraction accepts
unfenced code, and every harness call is guarded so the solver never crashes.
"""

import re

SYSTEM = (
    "You write small, correct Python functions from input/output examples. "
    "The function must be named f and take a single list argument xs."
)
ATTEMPTS = 4
FALLBACK = "def f(xs):\n    return list(xs)\n"
HINTS = [
    "First state the rule in one sentence, then check it against every example.",
    "Outputs often depend on position, length, prefix/suffix, neighbouring elements, "
    "running counts or running extremes, differences between neighbours, or sliding windows.",
    "The output length may differ from the input length; derive it from the rule.",
    "Do not print anything and do not read input; just define f.",
]


def extract(text):
    """Return code defining f, or '' if none can be found."""
    if not text:
        return ""
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.DOTALL)
    blocks = [b for b in blocks if re.search(r"def\s+f\s*\(", b)]
    if blocks:
        return blocks[-1]
    match = re.search(r"def\s+f\s*\(.*", text, re.DOTALL)
    if match:
        return match.group(0).strip() + "\n"
    return ""


def describe_failures(report):
    failed = [r for r in report if not r["passed"]]
    lines = []
    for r in failed[:4]:
        lines.append(
            f"f({r['input']}) returned {r['actual']}, expected {r['expected']}"
        )
    return "\n".join(lines)


def score_of(report):
    return sum(1 for r in report if r.get("passed"))


def solve(task, api):
    try:
        return _solve(task, api)
    except Exception:
        return FALLBACK


def _solve(task, api):
    shown = "\n".join(f"f({ex['input']}) == {ex['output']}" for ex in task["examples"])
    base = (
        "Write a Python function `def f(xs):` that maps a list of ints to a list of ints "
        "and is consistent with every example below. Use only the standard library.\n\n"
        + shown + "\n\n"
        + "".join(f"Hint: {hint}\n" for hint in HINTS)
        + "Return the code in one ```python block that defines def f."
    )
    prompt = base
    best_code, best_score = None, -1
    for _ in range(ATTEMPTS):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        except Exception:
            continue
        code = extract(reply)
        if not code:
            prompt = base + "\n\nYour last reply had no `def f(xs):`. Reply with a ```python block defining it."
            continue
        try:
            report = api.check(code)
        except api.BudgetExceeded:
            if best_code is None:
                best_code = code
            break
        except Exception:
            if best_code is None:
                best_code = code
            continue
        if all(r["passed"] for r in report):
            return code
        score = score_of(report)
        if score > best_score:
            best_code, best_score = code, score
        prompt = (
            base
            + "\n\nA previous attempt was:\n```python\n" + code + "```\n"
            + "It was wrong on these examples:\n" + describe_failures(report)
            + "\n\nFind the rule that fits all examples and return corrected code "
            + "defining f, in one ```python block."
        )
    return best_code if best_code else FALLBACK
