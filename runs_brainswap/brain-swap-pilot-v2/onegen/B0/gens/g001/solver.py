"""Example-driven solver with validation and hypothesis review."""

import re

SYSTEM = (
    "You infer precise list-to-list transformations from examples. "
    "Prefer simple, general rules over memorization. Pay close attention to "
    "order, duplicates, indices, negative numbers, and empty inputs."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^(?:from \S+ import .+|import .+|def f\s*\()", text)
    return text[match.start():].strip() if match else text.strip()


def check(api, code):
    try:
        report = api.check(code)
        return [r for r in report if not r["passed"]]
    except api.BudgetExceeded:
        return None
    except Exception:
        return None


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}"
        for ex in task["examples"]
    )
    prompt = (
        "Infer the intended transformation from ALL the examples below, then write "
        "Python code defining def f(xs), returning a list of integers.\n\n"
        + shown
        + "\n\nFirst reason about several plausible rules, including filtering, "
        "ordering, grouping, positional operations, arithmetic, and counts. "
        "Check each proposed rule against every example, especially duplicates and "
        "negative values. Distinguish accidental patterns from a consistent general "
        "rule. Handle empty and short lists. Do not memorize examples. "
        "Finally return the implementation in a single Python code block."
    )
    try:
        reply = api.llm(prompt, system=SYSTEM)
    except api.BudgetExceeded:
        return "def f(xs):\n    return []\n"

    code = extract(reply)
    failed = check(api, code)
    best = code
    best_failures = len(failed) if failed is not None else None

    for attempt in range(2):
        if failed:
            details = "\n".join(
                f"input={r['input']!r}, expected={r['expected']!r}, "
                f"actual={r['actual']!r}"
                for r in failed
            )
            review = (
                "The implementation fails these examples:\n" + details
                + "\nReconsider the underlying rule rather than patching examples."
            )
        else:
            review = (
                "The implementation may fit the visible examples but generalize "
                "poorly. Independently review the inferred rule against all examples. "
                "Consider competing simple rules, off-by-one errors, duplicates, "
                "ordering, negatives, and empty inputs. Keep the current rule if "
                "it is the best supported; otherwise correct it."
            )
        followup = (
            prompt + "\n\nPrevious response:\n" + reply + "\n\n" + review
            + "\nReturn the complete corrected function in one Python code block."
        )
        try:
            new_reply = api.llm(followup, system=SYSTEM)
        except api.BudgetExceeded:
            break
        new_code = extract(new_reply)
        new_failed = check(api, new_code)
        if new_failed is None:
            if best_failures is None:
                best = new_code
            break
        if best_failures is None or len(new_failed) <= best_failures:
            best, best_failures = new_code, len(new_failed)
            reply, failed = new_reply, new_failed
        if not new_failed:
            break
    return best
