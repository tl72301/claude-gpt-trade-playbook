"""Synthesize a list-to-list function from examples."""

import re

SYSTEM = (
    "You infer concise Python programs from input/output examples. "
    "Favor the simplest rule supported by all examples, not a memorized lookup."
)


def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    match = re.search(r"(?m)^(?:from \S+ import .*|import \S+|def f\s*\()", text)
    return text[match.start():].strip() if match else text.strip()


def solve(task, api):
    examples = "\n".join(
        "f(%r) == %r" % (example["input"], example["output"])
        for example in task["examples"]
    )
    prompt = (
        "Infer a general Python function def f(xs) returning a list of ints.\n"
        "Examples:\n" + examples + "\n\n"
        "Before coding, compare plausible simple rules against EVERY example, "
        "including output order and multiplicity. Consider values versus indices, "
        "filtering before versus after transforming, adjacent elements, and "
        "running state. Check whether a condition applies to the original value "
        "or a transformed value. Avoid assumptions based on a single example. "
        "When several rules fit, prefer a simple consistent rule and avoid "
        "special cases invented solely to fit the examples. Handle empty and "
        "short inputs and boundary values naturally. Use only the standard library. "
        "Return only executable code in a Python code block."
    )
    best_code = ""
    best_passed = -1
    feedback = ""
    for attempt in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            response = api.llm(prompt + feedback, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract(response)
        try:
            compile(code, "<candidate>", "exec")
        except (SyntaxError, ValueError, TypeError) as exc:
            feedback += "\nThe last code did not compile: %s. Return corrected code." % exc
            continue

        if not best_code:
            best_code = code
        try:
            if api.budget().get("checks", 0) <= 0:
                break
            results = api.check(code)
        except api.BudgetExceeded:
            break
        except Exception as exc:
            feedback += "\nThe last code could not be checked: %s. Correct it." % exc
            continue

        passed = sum(bool(item.get("passed")) for item in results)
        if passed > best_passed:
            best_passed = passed
            best_code = code
        failures = [item for item in results if not item.get("passed")]
        if not failures:
            return code
        details = "\n".join(
            "f(%r): got %r, expected %r" % (
                item.get("input"), item.get("actual"), item.get("expected")
            )
            for item in failures[:6]
        )
        feedback += (
            "\nThe previous candidate failed these shown examples:\n" + details
            + "\nReconsider the underlying rule and verify all examples. "
            "Return a complete replacement function."
        )

    return best_code or "def f(xs):\n    return []\n"
