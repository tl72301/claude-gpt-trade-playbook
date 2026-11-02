"""Infer a general list transformation from input/output examples."""
import re

SYSTEM = """You infer general Python list transformations from examples.
Consider complete, simple rules rather than memorizing values. Distinguish
selection, mapping, and ordering, and verify each proposed rule on every example."""

def extract(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text

def solve(task, api):
    shown = "\n".join(
        f"f({ex['input']!r}) == {ex['output']!r}" for ex in task["examples"]
    )
    prompt = (
        "Write def f(xs): returning a list of ints. Infer a general rule for unseen "
        "inputs from all these examples:\n\n" + shown +
        "\n\nReason carefully before writing code. Work backwards from each output: "
        "which input positions or values could produce it? An output need not be an "
        "input value: consider indices, arithmetic, remainders, and transformations "
        "of selected elements. Selection may depend on position, neighbors, adjacent "
        "pairs, earlier elements, or properties of the whole list, as well as the "
        "element itself. Consider filtering before or after mapping, original versus "
        "filtered indices, ordering, and duplicates. Use empty outputs as constraints.\n"
        "Compare multiple simple explanations that fit ALL examples, including "
        "boundary cases and negative numbers. Prefer a coherent composition over "
        "arbitrary constants or special cases. Test the chosen rule manually on "
        "every example. Handle empty and short inputs. Return only Python code in "
        "a fenced block."
    )
    best = ""
    best_failures = None
    for _ in range(3):
        try:
            if api.budget().get("llm_calls", 0) <= 0:
                break
            candidate = extract(api.llm(prompt, system=SYSTEM))
            if not best:
                best = candidate
            if api.budget().get("checks", 0) <= 0:
                break
            report = api.check(candidate)
            failed = [r for r in report if not r["passed"]]
            if best_failures is None or len(failed) < best_failures:
                best, best_failures = candidate, len(failed)
            if not failed:
                break
            details = "\n".join(
                f"f({r['input']!r}): got {r['actual']!r}, expected {r['expected']!r}"
                for r in failed
            )
            prompt += (
                "\n\nThe following candidate failed:\n" + candidate +
                "\nFailures:\n" + details +
                "\nReconsider selection, mapping, ordering, and contextual "
                "relationships from scratch. Return corrected code."
            )
        except api.BudgetExceeded:
            break
    return best
