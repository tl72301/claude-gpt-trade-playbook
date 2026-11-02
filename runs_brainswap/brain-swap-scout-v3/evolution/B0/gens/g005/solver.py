"""Infer and verify example-driven Python functions."""

import re


SYSTEM = (
    "Infer general list transformations from input/output examples. "
    "Use only the Python standard library. Define f(xs), returning a list "
    "of integers."
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
        return [r for r in api.check(code) if not r.get("passed")]
    except Exception:
        return None


def feedback(failed):
    if failed is None:
        return "Verification unavailable."
    if not failed:
        return "Passes all supplied examples, but hidden cases are not verified."
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
    common = (
        "Infer the intended general rule from ALL examples, then implement f(xs).\n"
        "Examine output lengths and order first. Consider compositions: filter "
        "or select elements or positions, then map them, count them, sort them, "
        "or compute running aggregates. Consider parity, divisibility, sign, "
        "absolute value, arithmetic, remainders, neighboring elements, index "
        "differences, prefix/suffix counts and sums, frequencies, ranks, and "
        "local or global comparisons. Scalar outputs may be wrapped in a list; "
        "repeated outputs may represent flags, not necessarily constants. "
        "For each plausible rule, manually test every example, including "
        "duplicates and negative numbers. Prefer a compact uniform rule over "
        "special cases, but do not assume the simplest guess is correct. "
        "Handle empty and short inputs and preserve the inferred ordering.\n\n"
        + examples
    )
    if remaining(api, "llm_calls") <= 0:
        return "def f(xs):\n    return []\n"

    candidates = []
    try:
        first = extract(api.llm(
            common + "\n\nReturn only complete executable Python code in a fenced block.",
            system=SYSTEM,
        ))
        candidates.append((first, verify(api, first)))
    except Exception:
        return "def f(xs):\n    return []\n"

    if remaining(api, "llm_calls") > 0:
        # Ask for an independent hypothesis rather than anchoring on the first code.
        try:
            second = extract(api.llm(
                common
                + "\n\nIndependently search for multiple competing explanations. "
                "Check their predictions on every example before choosing one. "
                "Pay particular attention to whether selection and transformation "
                "are separate steps. Return only complete executable Python code "
                "in a fenced block.",
                system=SYSTEM,
            ))
            candidates.append((second, verify(api, second)))
        except Exception:
            pass

    if remaining(api, "llm_calls") > 0:
        reports = []
        for i, (code, failed) in enumerate(candidates, 1):
            reports.append(
                f"Candidate {i}:\n```python\n{code}\n```\n{feedback(failed)}"
            )
        try:
            final = extract(api.llm(
                common
                + "\n\nReview the independently proposed solutions below. "
                "A candidate passing examples can still generalize poorly. "
                "Compare the actual rules, not just the code or pass status. "
                "Look for counterexamples among the supplied examples and "
                "for unjustified assumptions on unseen inputs. If neither rule "
                "is convincing, derive a better one. Do not memorize examples.\n\n"
                + "\n\n".join(reports)
                + "\n\nReturn only the best complete executable implementation "
                "in a Python fenced block.",
                system=SYSTEM,
            ))
            candidates.append((final, verify(api, final)))
        except Exception:
            pass

    # Prefer the reviewed candidate among equally verified implementations.
    passing = [code for code, failed in candidates if failed == []]
    if passing:
        return passing[-1]
    measured = [(len(failed), -i, code) for i, (code, failed) in enumerate(candidates)
                if failed is not None]
    if measured:
        return min(measured)[2]
    return candidates[-1][0]
