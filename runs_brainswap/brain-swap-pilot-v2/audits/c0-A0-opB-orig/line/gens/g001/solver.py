"""Infer a list transformation from examples and validate the proposed code."""

import re

SYSTEM = (
    "You infer small deterministic Python list transformations from examples. "
    "Generalization to unseen inputs matters more than fitting the displayed cases."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Infer the intended rule and write def f(xs), returning a list of ints.\n"
        "Examples:\n" + shown + "\n\n"
        "Consider several plausible simple rules before choosing one. Examine whether "
        "outputs correspond to input values, indices, adjacent pairs, running counts, "
        "remainders, or transformed values; determine filtering and ordering separately. "
        "Use every example, including empty outputs and duplicates, to distinguish "
        "hypotheses. Avoid arbitrary constants or special cases unless supported by "
        "the examples. Handle empty lists, negatives, and boundary cases naturally. "
        "Return only executable Python code in a single fenced block."
    )
    code = ""
    for attempt in range(3):
        try:
            reply = api.llm(prompt, system=SYSTEM)
            code = extract(reply)
            if not api.budget().get("checks", 0):
                break
            report = api.check(code)
        except api.BudgetExceeded:
            break
        failed = [r for r in report if not r["passed"]]
        if not failed:
            break
        details = "\n".join(
            f"f({r['input']!r}) returned {r['actual']!r}, expected {r['expected']!r}"
            for r in failed
        )
        prompt += (
            "\n\nThe following proposed code failed the shown examples:\n"
            + code + "\nFailures:\n" + details
            + "\nReconsider the rule, check it against all examples, and return corrected code."
        )
    return code
