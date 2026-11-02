"""Grade a candidate f(xs) program: one sandboxed process per (program, input set).

Expected outputs never enter the sandbox -- the program only receives inputs,
and outputs are compared here, in the harness.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from rsi.sandbox import SAFE_ENV, Sandbox, kill_group, limit_prefix, wrap_command

RUNNER = '''
import json, os, sys
data = json.loads(sys.stdin.read())
out = os.fdopen(os.dup(1), "w")
os.dup2(2, 1)
sys.stdout = sys.stderr
def emit(obj):
    out.write(json.dumps(obj)); out.flush()
ns = {"__name__": "candidate"}
try:
    exec(compile(data["code"], "<candidate>", "exec"), ns)
    f = ns["f"]
except BaseException as e:
    emit({"error": f"{type(e).__name__}: {e}"[:300]}); raise SystemExit(0)
res = []
for x in data["inputs"]:
    try:
        y = f(list(x))
        ok = isinstance(y, list) and all(type(v) is int for v in y)
        res.append(y if ok else {"bad": repr(y)[:80]})
    except BaseException as e:
        res.append({"bad": type(e).__name__})
emit({"outputs": res})
'''


def _run_inprocess(code: str, inputs: list[list[int]]) -> dict:
    ns = {"__name__": "candidate"}
    try:
        exec(compile(code, "<candidate>", "exec"), ns)
        f = ns["f"]
    except BaseException as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"[:300]}
    res = []
    for x in inputs:
        try:
            y = f(list(x))
            ok = isinstance(y, list) and all(type(v) is int for v in y)
            res.append(y if ok else {"bad": repr(y)[:80]})
        except BaseException as e:  # noqa: BLE001
            res.append({"bad": type(e).__name__})
    return json.loads(json.dumps({"outputs": res}))


def run_program(code: str, inputs: list[list[int]], sandbox: Sandbox, timeout_s: float = 5.0) -> dict:
    """{"outputs": [...]} or {"error": str}. Each output is a list or {"bad": ...}."""
    if getattr(sandbox, "isolation", None) == "inprocess":  # mock runs only
        return _run_inprocess(code, inputs)
    with tempfile.TemporaryDirectory(prefix="bs-grade-") as d:
        runner = Path(d, "runner.py")
        runner.write_text(RUNNER)
        script = str(runner) if sandbox.isolation == "none" else "/work/runner.py"
        cmd = limit_prefix(sandbox.mem_mb, int(timeout_s) + 1) + wrap_command(
            [sys.executable, "-I", "-S", script], sandbox.isolation, d)
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, cwd=d, env=SAFE_ENV,
                                start_new_session=True)
        try:
            out, _ = proc.communicate(json.dumps({"code": code, "inputs": inputs}).encode(), timeout=timeout_s)
        except subprocess.TimeoutExpired:
            kill_group(proc)
            proc.communicate()
            return {"error": "timeout"}
    try:
        return json.loads(out.decode() or "{}") or {"error": "no output"}
    except ValueError:
        return {"error": "unreadable output"}


def grade(code: str, tests: list[dict], sandbox: Sandbox) -> dict:
    """{"passed", "n_passed", "n", "failure"}; failure = first mismatch (for shown examples only)."""
    if not code or "def f" not in code:
        return {"passed": False, "n_passed": 0, "n": len(tests), "failure": "no function f"}
    r = run_program(code, [t["input"] for t in tests], sandbox)
    if "error" in r:
        return {"passed": False, "n_passed": 0, "n": len(tests), "failure": r["error"]}
    outs = r.get("outputs", [])
    n_passed, first = 0, None
    for t, o in zip(tests, outs):
        if o == t["output"]:
            n_passed += 1
        elif first is None:
            first = {"input": t["input"], "expected": t["output"], "actual": o}
    return {"passed": n_passed == len(tests), "n_passed": n_passed, "n": len(tests),
            "failure": first}


def check_examples(code: str, examples: list[dict], sandbox: Sandbox) -> list[dict]:
    """Per-example report for api.check (examples are already visible to the agent)."""
    if not code or "def f" not in code:
        return [{"passed": False, "input": e["input"], "expected": e["output"], "actual": "no function f"}
                for e in examples]
    r = run_program(code, [e["input"] for e in examples], sandbox)
    outs = r.get("outputs") or [r.get("error", "error")] * len(examples)
    return [{"passed": o == e["output"], "input": e["input"], "expected": e["output"], "actual": o}
            for e, o in zip(examples, outs)]
