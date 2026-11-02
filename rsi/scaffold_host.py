"""Runs one scaffold (``solver.py``) on one problem, inside the sandbox.

STDLIB ONLY: this file is mounted into the sandbox on its own and cannot import
the ``rsi`` package.

The scaffold never talks to the model API or the grader directly. It gets an
``api`` object whose methods send requests up a pipe to the harness, which
holds the API key, enforces the per-problem budget, and always uses the fixed
solver model. So a scaffold cannot quietly switch to a stronger model, exceed
its budget, or see hidden tests -- it only ever receives the problem statement
and public tests.

Protocol (one JSON object per line):
  harness -> host : {"problem": {...}}           (first line)
  host -> harness : {"type": "llm" | "run" | "public_tests" | "budget" | "final" | "crash", ...}
  harness -> host : one reply line per request
"""

import importlib.util
import json
import os
import sys
import traceback


class BudgetExceeded(Exception):
    """Raised by api.llm / api.run when the per-problem budget is spent."""


class Api:
    """The only interface a scaffold has to the outside world.

    api.llm(prompt=None, *, messages=None, system=None, max_tokens=None) -> str
        One call to the fixed solver model. Returns the text ("" if it refused).
        Raises api.BudgetExceeded when out of calls or tokens.
    api.run(code, stdin="", timeout_s=None) -> dict
        Run a Python 3 program in the sandbox.
        Returns {"stdout", "stderr", "returncode", "timed_out"}.
    api.run_public_tests(code) -> list[dict]
        Run a program on this problem's public tests. Each result:
        {"passed", "input", "expected", "actual", "stderr", "timed_out"}.
    api.budget() -> dict
        Remaining {"llm_calls", "output_tokens", "runs", "seconds"}.
    """

    BudgetExceeded = BudgetExceeded

    def __init__(self, rx, tx):
        self._rx = rx
        self._tx = tx
        self.last_stop_reason = None

    def _call(self, payload):
        self._tx.write(json.dumps(payload) + "\n")
        self._tx.flush()
        line = self._rx.readline()
        if not line:
            raise SystemExit(3)
        resp = json.loads(line)
        if resp.get("error") == "budget":
            raise BudgetExceeded(resp.get("detail", "budget exhausted"))
        if "error" in resp:
            raise RuntimeError(resp["error"])
        return resp

    def llm(self, prompt=None, *, messages=None, system=None, max_tokens=None):
        if messages is None:
            if prompt is None:
                raise ValueError("api.llm needs prompt or messages")
            messages = [{"role": "user", "content": prompt}]
        resp = self._call({"type": "llm", "messages": messages, "system": system,
                           "max_tokens": max_tokens})
        self.last_stop_reason = resp.get("stop_reason")
        return resp.get("text", "")

    def run(self, code, stdin="", timeout_s=None):
        return self._call({"type": "run", "code": code, "stdin": stdin, "timeout_s": timeout_s})

    def run_public_tests(self, code):
        return self._call({"type": "public_tests", "code": code})["results"]

    def budget(self):
        return self._call({"type": "budget"})


def main():
    scaffold_path = sys.argv[1]
    # Keep private handles to the protocol pipes, then point the scaffold's
    # stdin at /dev/null and its stdout at stderr so prints can't corrupt them.
    tx = os.fdopen(os.dup(1), "w", encoding="utf-8")
    rx = os.fdopen(os.dup(0), "r", encoding="utf-8")
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    os.dup2(2, 1)
    sys.stdin = open(os.devnull)
    sys.stdout = sys.stderr

    problem = json.loads(rx.readline())["problem"]
    api = Api(rx, tx)
    try:
        spec = importlib.util.spec_from_file_location("solver", scaffold_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        code = module.solve(problem, api)
        msg = {"type": "final", "code": code if isinstance(code, str) else None}
    except BaseException:  # noqa: BLE001 -- report everything, including SystemExit
        msg = {"type": "crash", "error": traceback.format_exc()[-4000:]}
    tx.write(json.dumps(msg) + "\n")
    tx.flush()


if __name__ == "__main__":
    main()
