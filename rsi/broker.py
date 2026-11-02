"""Harness side of the scaffold protocol (see scaffold_host.py).

Launches the host in the sandbox, answers its requests, and enforces the
per-problem budget. This is the only place solver-model calls happen.
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .llm import LLM
from .sandbox import SAFE_ENV, Sandbox, kill_group, limit_prefix, wrap_command

HOST = Path(__file__).with_name("scaffold_host.py")
RUN_STDOUT_KEEP = 20_000   # chars of a sandbox run's stdout returned to the scaffold
TEST_TEXT_KEEP = 2_000     # chars of each public-test field returned to the scaffold


@dataclass
class Budget:
    llm_calls: int = 8
    output_tokens: int = 60_000
    runs: int = 60
    wall_seconds: float = 900.0
    run_timeout_s: float = 10.0

    @classmethod
    def from_cfg(cls, cfg: dict) -> "Budget":
        return cls(**{k: cfg[k] for k in cls.__dataclass_fields__ if k in cfg})


@dataclass
class ScaffoldRun:
    code: str | None = None
    status: str = "pending"      # ok | crash | timeout | no_output | protocol_error
    error: str | None = None
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    sandbox_runs: int = 0
    refusals: list[dict] = field(default_factory=list)
    model_mismatches: int = 0
    stderr_tail: str = ""
    wall_s: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _clip(s: str | None, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + f"\n...[{len(s) - n} more chars]"


def _valid_messages(msgs) -> bool:
    """Plain text only. Image/document blocks can carry URLs that the API server
    would fetch -- network reach from outside the sandbox -- so they're rejected,
    along with tool blocks and anything else that isn't text."""
    if not isinstance(msgs, list) or not msgs:
        return False
    for m in msgs:
        if not isinstance(m, dict) or set(m) != {"role", "content"}:
            return False
        if m["role"] not in ("user", "assistant"):
            return False
        content = m["content"]
        if isinstance(content, str):
            continue
        if not isinstance(content, list) or not content:
            return False
        for block in content:
            if not (isinstance(block, dict) and set(block) == {"type", "text"}
                    and block["type"] == "text" and isinstance(block["text"], str)):
                return False
    return True


def public_view(task: dict) -> dict:
    """Everything a scaffold may see about a problem. Hidden tests never leave the harness."""
    return {
        "id": task["id"],
        "title": task.get("title", ""),
        "statement": task["statement"],
        "public_tests": [{"input": t["input"], "output": t["output"]} for t in task["public_tests"]],
        "time_limit_s": task.get("time_limit_s", 6),
    }


def run_scaffold(scaffold_path: Path, task: dict, llm: LLM, sandbox: Sandbox,
                 budget: Budget, context: dict | None = None) -> ScaffoldRun:
    result = ScaffoldRun()
    problem = public_view(task)
    run_timeout = min(float(problem["time_limit_s"]), budget.run_timeout_s)
    start = time.monotonic()
    deadline = start + budget.wall_seconds

    with tempfile.TemporaryDirectory(prefix="rsi-host-") as workdir:
        if sandbox.isolation == "none":
            inner = [sys.executable, "-I", "-S", str(HOST), str(Path(scaffold_path).resolve())]
            ro = None
        else:
            inner = [sys.executable, "-I", "-S", "/opt/rsi/scaffold_host.py", "/opt/rsi/solver.py"]
            ro = {"/opt/rsi/scaffold_host.py": str(HOST),
                  "/opt/rsi/solver.py": str(Path(scaffold_path).resolve())}
        cmd = limit_prefix(2048, int(budget.wall_seconds) + 5) + wrap_command(
            inner, sandbox.isolation, workdir, ro)
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, cwd=workdir, env=SAFE_ENV,
                                text=True, encoding="utf-8", errors="replace",
                                start_new_session=True, bufsize=1)
        lines: queue.Queue = queue.Queue()
        stderr_buf: list[str] = []

        def read_stdout():
            for line in proc.stdout:
                lines.put(line)
            lines.put(None)

        def read_stderr():
            kept = 0
            for line in proc.stderr:
                stderr_buf.append(line)
                kept += len(line)
                while kept > 8000 and len(stderr_buf) > 1:
                    kept -= len(stderr_buf.pop(0))

        threads = [threading.Thread(target=read_stdout, daemon=True),
                   threading.Thread(target=read_stderr, daemon=True)]
        for t in threads:
            t.start()

        def reply(obj: dict) -> bool:
            try:
                proc.stdin.write(json.dumps(obj) + "\n")
                proc.stdin.flush()
                return True
            except (BrokenPipeError, OSError):
                return False

        reply({"problem": problem})
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    result.status, result.error = "timeout", "scaffold exceeded wall budget"
                    break
                try:
                    line = lines.get(timeout=min(remaining, 5.0))
                except queue.Empty:
                    continue
                if line is None:
                    result.status = "no_output"
                    result.error = "scaffold exited without returning a program"
                    break
                try:
                    msg = json.loads(line)
                    kind = msg["type"]
                except (ValueError, KeyError, TypeError):
                    result.status, result.error = "protocol_error", _clip(line, 500)
                    break

                if kind == "final":
                    result.code = msg.get("code")
                    result.status = "ok" if result.code else "no_output"
                    break
                if kind == "crash":
                    result.status, result.error = "crash", msg.get("error")
                    break
                if kind == "budget":
                    ok = reply({
                        "llm_calls": budget.llm_calls - result.llm_calls,
                        "output_tokens": budget.output_tokens - result.output_tokens,
                        "runs": budget.runs - result.sandbox_runs,
                        "seconds": round(deadline - time.monotonic(), 1),
                    })
                elif kind == "llm":
                    if (result.llm_calls >= budget.llm_calls
                            or result.output_tokens >= budget.output_tokens):
                        ok = reply({"error": "budget", "detail": "solver call budget exhausted"})
                    elif (not _valid_messages(msg.get("messages"))
                          or not isinstance(msg.get("system") or "", str)):
                        ok = reply({"error": "invalid messages: plain text content only"})
                    else:
                        cap = budget.output_tokens - result.output_tokens
                        req = msg.get("max_tokens")
                        max_tokens = min(int(req), cap) if isinstance(req, int) and req > 0 else None
                        if max_tokens is None and llm_default_max(llm) > cap:
                            max_tokens = cap
                        ctx = dict(context or {}, role="solver", task_id=task["id"],
                                   call_index=result.llm_calls)
                        result.llm_calls += 1
                        try:
                            r = llm.complete(msg["messages"], system=msg.get("system") or None,
                                             max_tokens=max_tokens, context=ctx)
                        except Exception as e:  # network errors etc. after SDK retries
                            ok = reply({"error": f"llm_error: {type(e).__name__}: {_clip(str(e), 300)}"})
                        else:
                            result.input_tokens += r.input_tokens
                            result.output_tokens += r.output_tokens
                            result.cost_usd += r.cost_usd
                            if r.refused:
                                result.refusals.append({"category": r.refusal_category,
                                                        "explanation": r.refusal_explanation})
                            if r.model_mismatch:
                                result.model_mismatches += 1
                            ok = reply({"text": r.text, "stop_reason": r.stop_reason,
                                        "refused": r.refused})
                elif kind in ("run", "public_tests"):
                    if result.sandbox_runs >= budget.runs:
                        ok = reply({"error": "budget", "detail": "sandbox run budget exhausted"})
                    elif not isinstance(msg.get("code"), str):
                        ok = reply({"error": "code must be a string"})
                    elif kind == "run":
                        result.sandbox_runs += 1
                        t = msg.get("timeout_s")
                        t = min(float(t), run_timeout) if isinstance(t, (int, float)) and t > 0 else run_timeout
                        r = sandbox.run(msg["code"], str(msg.get("stdin") or ""), t)
                        d = r.to_dict()
                        d["stdout"] = _clip(d["stdout"], RUN_STDOUT_KEEP)
                        ok = reply(d)
                    else:
                        out = []
                        for test in problem["public_tests"]:
                            result.sandbox_runs += 1
                            g = sandbox.grade(msg["code"], [test], run_timeout)
                            fr = g.failure_run
                            out.append({
                                "passed": g.passed,
                                "input": _clip(test["input"], TEST_TEXT_KEEP),
                                "expected": _clip(test["output"], TEST_TEXT_KEEP),
                                "actual": _clip(fr.stdout if fr else test["output"], TEST_TEXT_KEEP),
                                "stderr": _clip(fr.stderr if fr else "", TEST_TEXT_KEEP),
                                "timed_out": bool(fr and fr.timed_out),
                            })
                        ok = reply({"results": out})
                else:
                    ok = reply({"error": f"unknown request type {kind!r}"})
                if not ok:
                    result.status, result.error = "crash", "scaffold closed its pipe"
                    break
        finally:
            kill_group(proc)
            proc.wait()
            for t in threads:
                t.join(timeout=2)
            result.stderr_tail = "".join(stderr_buf)[-4000:]
            result.wall_s = round(time.monotonic() - start, 2)
    return result


def llm_default_max(llm: LLM) -> int:
    return int(getattr(llm, "max_tokens", 16000))
