"""In-sandbox host for one agent entry point. STDLIB ONLY (mounted alone into the sandbox).

    python host.py <role> <path-to-entry-file>
      role = solver   -> calls solve(task, api)
      role = improver -> calls improve(ctx, api)

The agent never holds an API key, a file handle, or a network socket. Every
api.* call is one JSON line to the harness, which answers, meters the budget,
and decides which model serves api.llm. Protocol:
  harness -> host : {"payload": {...}}                      (first line)
  host -> harness : {"type": <method>, ...}  /  {"type": "final", "value": ...}
  harness -> host : one reply line per request
"""

import importlib.util
import json
import os
import sys
import traceback


class BudgetExceeded(Exception):
    pass


class Api:
    BudgetExceeded = BudgetExceeded

    def __init__(self, rx, tx, role):
        self._rx, self._tx, self._role = rx, tx, role

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
        return resp["value"]

    def llm(self, prompt=None, *, messages=None, system=None, max_tokens=None):
        if messages is None:
            if prompt is None:
                raise ValueError("api.llm needs prompt or messages")
            messages = [{"role": "user", "content": prompt}]
        return self._call({"type": "llm", "messages": messages, "system": system,
                           "max_tokens": max_tokens})

    def budget(self):
        return self._call({"type": "budget"})

    # solver role
    def check(self, code):
        return self._call({"type": "check", "code": code})

    # improver role
    def source(self, name):
        return self._call({"type": "source", "name": name})

    def trial(self, solver_source, n):
        return self._call({"type": "trial", "source": solver_source, "n": n})


def main():
    role, path = sys.argv[1], sys.argv[2]
    tx = os.fdopen(os.dup(1), "w", encoding="utf-8")
    rx = os.fdopen(os.dup(0), "r", encoding="utf-8")
    os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
    os.dup2(2, 1)
    sys.stdin, sys.stdout = open(os.devnull), sys.stderr
    payload = json.loads(rx.readline())["payload"]
    api = Api(rx, tx, role)
    try:
        spec = importlib.util.spec_from_file_location("agent_" + role, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        value = (module.solve if role == "solver" else module.improve)(payload, api)
        msg = {"type": "final", "value": value}
        json.dumps(msg)
    except BaseException:  # noqa: BLE001
        msg = {"type": "crash", "error": traceback.format_exc()[-3000:]}
    tx.write(json.dumps(msg) + "\n")
    tx.flush()


if __name__ == "__main__":
    main()
