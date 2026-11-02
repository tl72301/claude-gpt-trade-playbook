"""Deterministic stand-in models for offline runs (``--mock``) and CI.

The mock solver "knows" each dev task's reference solution and succeeds with a
per-task probability that rises when it is shown test feedback. So a scaffold
that tests and retries really does score higher than the one-shot seed, and the
whole loop -- broker, grader, policy checks, accept/reject, held-out, report --
produces a believable curve with no API key.

The mock improver follows a fixed schedule that also exercises the failure
paths: a policy violation, a malformed reply, and a ``frontier_llm`` refusal.
"""

from __future__ import annotations

import hashlib

from .llm import LLMResult, price_entry, request_cost

IMPROVED_TEMPLATE = '''"""Test-and-retry scaffold (mock improver, generation {gen})."""

import re

ATTEMPTS = {attempts}
SYSTEM = (
    "You are an expert competitive programmer. Solve the problem in Python 3. "
    "Read from standard input and write to standard output."
)


def extract_code(text):
    blocks = re.findall(r"```(?:python|py)?\\s*\\n(.*?)```", text, re.DOTALL)
    return max(blocks, key=len) if blocks else text


def solve(problem, api):
    messages = [{{"role": "user", "content": (
        problem["statement"] + "\\n\\nWrite a complete Python 3 program. "
        "Return only the code in a single ```python block.")}}]
    best = ""
    for _ in range(ATTEMPTS):
        try:
            reply = api.llm(messages=messages, system=SYSTEM)
        except api.BudgetExceeded:
            break
        code = extract_code(reply)
        best = code or best
        results = api.run_public_tests(code)
        failed = [r for r in results if not r["passed"]]
        if not failed:
            return code
        f = failed[0]
        messages += [
            {{"role": "assistant", "content": reply}},
            {{"role": "user", "content": (
                "Your program did not pass a public test.\\n"
                f"Input:\\n{{f['input']}}\\nExpected:\\n{{f['expected']}}\\n"
                f"Got:\\n{{f['actual']}}\\nStderr:\\n{{f['stderr']}}\\n"
                "Fix it and return the full program.")}},
        ]
    return best
'''

VIOLATION_SCAFFOLD = '''import os


def solve(problem, api):
    # Tries to read the task file directly. The policy check must reject this.
    with open(os.path.join("data", "tasks.jsonl")) as f:
        return f.read()
'''


def unit(*parts) -> float:
    """Deterministic pseudo-random number in [0, 1) from the given parts."""
    h = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def _text_len(messages, system) -> int:
    n = len(system or "")
    for m in messages:
        c = m.get("content")
        n += len(c) if isinstance(c, str) else sum(len(str(x)) for x in c)
    return n


class MockLLM:
    def __init__(self, model: str, prices: dict, role: str, tasks: list[dict]):
        self.model = model
        self.role = role
        self.max_tokens = 16000
        self.tasks = {t["id"]: t for t in tasks}
        self.price = price_entry(model, prices)

    def _result(self, text, messages, system, stop_reason="end_turn", **extra) -> LLMResult:
        in_tok = _text_len(messages, system) // 4
        out_tok = len(text) // 4 + 400  # pretend some thinking happened
        return LLMResult(text=text, requested_model=self.model, served_model=self.model,
                         stop_reason=stop_reason, input_tokens=in_tok, output_tokens=out_tok,
                         cost_usd=request_cost(self.price, in_tok, out_tok),
                         **extra)

    def complete(self, messages, system=None, max_tokens=None, context=None) -> LLMResult:
        context = context or {}
        if context.get("role", self.role) == "improver":
            return self._improver(messages, system, context)
        return self._solver(messages, system, context)

    # ---- solver -----------------------------------------------------------
    def _solver(self, messages, system, ctx) -> LLMResult:
        task = self.tasks.get(ctx.get("task_id"))
        if task is None:
            return self._result("```python\nprint(0)\n```", messages, system)
        last = messages[-1].get("content", "")
        feedback = isinstance(last, str) and "did not pass" in last
        p_correct = 0.15 + 0.45 * unit("task", task["id"]) + (0.25 if feedback else 0.0)
        draw = unit(task["id"], ctx.get("nonce"), ctx.get("call_index"))
        if draw < p_correct:
            code = task["reference_solution"]
        elif draw < p_correct + 0.2:
            # Passes the public tests, fails hidden ones -- the classic overfit.
            cases = {t["input"].strip(): t["output"] for t in task["public_tests"]}
            code = ("import sys\ncases = " + repr(cases) +
                    "\ndata = sys.stdin.read().strip()\nprint(cases.get(data, '0'), end='')")
        else:
            code = "print(0)"
        return self._result(f"```python\n{code}\n```", messages, system)

    # ---- improver ---------------------------------------------------------
    def _improver(self, messages, system, ctx) -> LLMResult:
        gen = int(ctx.get("generation", 1))
        if gen == 4:
            return self._result("", messages, system, stop_reason="refusal",
                                refusal_category="frontier_llm",
                                refusal_explanation="(mock) declined as frontier LLM development")
        if gen == 3:
            body = VIOLATION_SCAFFOLD
        elif gen == 6:
            return self._result("I think the scaffold is fine as it is.", messages, system)
        else:
            body = IMPROVED_TEMPLATE.format(gen=gen, attempts=min(1 + gen, 6))
        text = (
            f"<analysis>(mock) Generation {gen}: add test-and-retry with feedback.</analysis>\n"
            f"<solver_py>\n{body}</solver_py>\n"
            f"<notebook_entry>(mock) Gen {gen}: retries with public-test feedback help; "
            f"watch for programs that only memorize the public cases.</notebook_entry>\n"
        )
        return self._result(text, messages, system)
