"""Example-based Python function synthesizer."""

import re

SYSTEM = (
    "You are an expert at inferring compact list-processing programs from examples. "
    "Infer the underlying general rule, not a lookup table. Be precise about order, "
    "duplicates, indices, negative integers, and empty inputs."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^(?:from .+ import .+\n|import .+\n)*def f\(xs\):", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer a single deterministic Python function f(xs) mapping a list of integers "
        "to a list of integers. All examples come from the same small general rule.\n\n"
        + shown
        + "\n\nFirst reason carefully through multiple plausible rules against EVERY "
        "example, including exact output length, ordering, repeated values and negative "
        "numbers. Consider filters, transformations, adjacent elements, positions, "
        "counts, ranks, arithmetic and modular patterns as appropriate. Prefer a simple "
        "rule that explains all the evidence; do not memorize examples. Then give the "
        "complete implementation in a final Python code block. Handle empty and short "
        "inputs naturally. Use only the standard library."
    )
    best = ""
    best_passed = -1
    feedback = ""
    for attempt in range(3):
        try:
            if attempt == 0:
                query = prompt
            else:
                query = (
                    prompt + "\n\nA previous candidate was:\n```python\n" + best
                    + "\n```\n" + feedback
                    + "\nIndependently reconsider the intended rule. Check competing "
                    "hypotheses against the examples and look for overfitting, subtle "
                    "boundary errors, and alternative interpretations. If the candidate "
                    "is sound, retain it; otherwise improve it. Return a complete final "
                    "implementation in a Python code block."
                )
            reply = api.llm(query, system=SYSTEM)
            code = extract(reply)
            if not code:
                continue
            try:
                report = api.check(code)
            except api.BudgetExceeded:
                if not best:
                    best = code
                break
            passed = sum(bool(r["passed"]) for r in report)
            failed = [r for r in report if not r["passed"]]
            if passed > best_passed or (passed == best_passed and not failed):
                best, best_passed = code, passed
            if failed:
                feedback = "Candidate failed shown examples:\n" + "\n".join(
                    f"f({r['input']!r}): got {r['actual']!r}, expected {r['expected']!r}"
                    for r in failed[:4]
                )
            else:
                feedback = (
                    "The candidate passes all shown examples, but this does not prove "
                    "it generalizes. Examine whether another simple rule better explains "
                    "the evidence, especially for unseen inputs."
                )
                if attempt >= 1:
                    break
        except api.BudgetExceeded:
            break
    return best or "def f(xs):\n    return []\n"
