"""Infer and verify example-driven Python functions."""

import re


SYSTEM = (
    "You infer general Python list transformations from input/output examples. "
    "Use only the Python standard library. Define f(xs), returning a list of integers."
)


def extract(text):
    blocks = re.findall(
        r"```(?:python|py)?[ \t]*\n(.*?)```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^(?:from \S+ import |import \S+|def f\s*\()", text)
    return text[match.start():].strip() if match else text.strip()


def remaining(api, key):
    try:
        return api.budget().get(key, 0)
    except Exception:
        return 0


def verify(api, code):
    if remaining(api, "checks") <= 0:
        return None
    try:
        report = api.check(code)
        return [r for r in report if not r.get("passed")]
    except Exception:
        return None


def feedback(failed):
    if failed is None:
        return "Verification unavailable."
    if not failed:
        return "The candidate passes all provided examples."
    return "Failed examples:\n" + "\n".join(
        f"input={r.get('input')!r}, expected={r.get('expected')!r}, "
        f"actual={r.get('actual')!r}"
        for r in failed
    )


def solve(task, api):
    examples = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}"
        for ex in task["examples"]
    )
    prompt = (
        "Infer the intended general rule and implement def f(xs).\n\n"
        + examples
        + "\n\nAnalyze all examples before coding. Consider transformations of "
        "individual values, indices, adjacent values, prefixes and suffixes, "
        "counts, sorting, filtering, and aggregates. Outputs may encode counts "
        "or flags rather than selected input values. Look for a single consistent "
        "rule, including output order, duplicates, signs, and ties. Do not "
        "memorize examples or infer a constant merely because outputs coincide. "
        "Prefer simple operations and handle empty and short inputs naturally. "
        "Return only complete executable Python code in a fenced block."
    )
    if remaining(api, "llm_calls") <= 0:
        return "def f(xs):\n    return []\n"
    try:
        first = extract(api.llm(prompt, system=SYSTEM))
    except Exception:
        return "def f(xs):\n    return []\n"
    first_failed = verify(api, first)

    if remaining(api, "llm_calls") <= 0:
        return first
    review = (
        "Independently solve this example-driven task, then scrutinize the "
        "candidate. A solution fitting the examples can still be wrong on hidden "
        "inputs. Compare plausible rules and inspect evidence from every example; "
        "pay special attention to indexing, boundaries, strict comparisons, "
        "duplicates, order, and whether an output is a count, value, or flag. "
        "Avoid special-casing the supplied examples.\n\n"
        + examples
        + "\n\nCandidate:\n```python\n"
        + first
        + "\n```\n"
        + feedback(first_failed)
        + "\n\nReturn only the best complete implementation of f(xs) in a "
        "Python code block."
    )
    try:
        second = extract(api.llm(review, system=SYSTEM))
    except Exception:
        return first
    second_failed = verify(api, second)

    if second_failed == []:
        return second
    if first_failed == []:
        return first

    if remaining(api, "llm_calls") > 0:
        correction = (
            "Reconsider the transformation from scratch. The proposed code does "
            "not satisfy all examples. Find one general rule explaining every "
            "example, including output order and ties. Return only complete "
            "Python code defining f(xs).\n\n"
            + examples
            + "\n\nCandidate:\n```python\n"
            + second
            + "\n```\n"
            + feedback(second_failed)
            + "\n\nEarlier candidate:\n```python\n"
            + first
            + "\n```\n"
            + feedback(first_failed)
        )
        try:
            third = extract(api.llm(correction, system=SYSTEM))
            third_failed = verify(api, third)
            if third_failed == []:
                return third
            if third_failed is None and second_failed is None:
                return third
            if third_failed is not None:
                candidates = [(len(third_failed), third)]
                if first_failed is not None:
                    candidates.append((len(first_failed), first))
                if second_failed is not None:
                    candidates.append((len(second_failed), second))
                return min(candidates, key=lambda item: item[0])[1]
        except Exception:
            pass

    if first_failed is not None and second_failed is not None:
        return first if len(first_failed) < len(second_failed) else second
    if first_failed is not None:
        return first
    return second
