"""Harness side of the host protocol: run one agent entry point in the sandbox and
answer its api.* requests through role-specific handlers."""

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

from rsi.broker import _valid_messages
from rsi.sandbox import SAFE_ENV, Sandbox, kill_group, limit_prefix, wrap_command

HOST = Path(__file__).with_name("host.py")


class BudgetError(Exception):
    """Raised by a handler when the request would exceed the budget."""


@dataclass
class EntryResult:
    value: object = None
    status: str = "pending"      # ok | crash | timeout | no_output | protocol_error
    error: str | None = None
    wall_s: float = 0.0
    stderr_tail: str = ""

    def to_dict(self):
        return asdict(self)


def valid_llm_request(msg: dict) -> bool:
    return _valid_messages(msg.get("messages")) and isinstance(msg.get("system") or "", str)


class InProcess:
    """Run agent code inside the harness process. ONLY for mock runs, where every
    line of agent code and every program is produced by the deterministic mock.
    Real models always run sandboxed (enforced in experiment.py)."""
    isolation = "inprocess"
    mem_mb = 1024


def _run_inprocess(role, entry_source, payload, handlers) -> EntryResult:
    import importlib.util  # noqa: F401  (kept for parity with host.py)
    import json as _json
    import traceback

    spec = importlib.util.spec_from_file_location("bs_host", HOST)
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)

    class Api(host.Api):
        def __init__(self):
            pass

        def _call(self, msg):
            handler = handlers.get(msg["type"])
            if handler is None:
                raise RuntimeError(f"api.{msg['type']} is not available to the {role}")
            msg = _json.loads(_json.dumps(msg))
            try:
                return _json.loads(_json.dumps(handler(msg)))
            except BudgetError as e:
                raise host.BudgetExceeded(str(e))
            except (ValueError, TypeError) as e:
                raise RuntimeError(f"bad request: {e}")

    res = EntryResult()
    start = time.monotonic()
    ns = {"__name__": "agent_" + role}
    try:
        exec(compile(entry_source, f"<{role}>", "exec"), ns)
        value = ns["solve" if role == "solver" else "improve"](_json.loads(_json.dumps(payload)), Api())
        res.value, res.status = _json.loads(_json.dumps(value)), "ok"
    except Exception:  # noqa: BLE001
        res.status, res.error = "crash", traceback.format_exc()[-3000:]
    res.wall_s = round(time.monotonic() - start, 2)
    return res


def run_entry(role: str, entry_source: str, payload: dict, handlers: dict, sandbox: Sandbox,
              wall_seconds: float) -> EntryResult:
    if getattr(sandbox, "isolation", None) == "inprocess":
        return _run_inprocess(role, entry_source, payload, handlers)
    res = EntryResult()
    start = time.monotonic()
    deadline = start + wall_seconds
    with tempfile.TemporaryDirectory(prefix=f"bs-{role}-") as work:
        entry = Path(work, f"{role}.py")
        entry.write_text(entry_source)
        if sandbox.isolation == "none":
            inner = [sys.executable, "-I", "-S", str(HOST), role, str(entry)]
            ro = None
        else:
            inner = [sys.executable, "-I", "-S", "/opt/bs/host.py", role, "/opt/bs/entry.py"]
            ro = {"/opt/bs/host.py": str(HOST), "/opt/bs/entry.py": str(entry)}
        cmd = limit_prefix(2048, int(wall_seconds) + 5) + wrap_command(inner, sandbox.isolation, work, ro)
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=work, env=SAFE_ENV, text=True, encoding="utf-8", errors="replace",
                                start_new_session=True, bufsize=1)
        lines: queue.Queue = queue.Queue()
        err: list[str] = []

        def pump_out():
            for line in proc.stdout:
                lines.put(line)
            lines.put(None)

        def pump_err():
            for line in proc.stderr:
                err.append(line)
                if len(err) > 200:
                    del err[:100]

        threads = [threading.Thread(target=pump_out, daemon=True), threading.Thread(target=pump_err, daemon=True)]
        for t in threads:
            t.start()

        def reply(obj) -> bool:
            try:
                proc.stdin.write(json.dumps(obj) + "\n")
                proc.stdin.flush()
                return True
            except (BrokenPipeError, OSError):
                return False

        reply({"payload": payload})
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    res.status, res.error = "timeout", "wall budget exceeded"
                    break
                try:
                    line = lines.get(timeout=min(remaining, 5.0))
                except queue.Empty:
                    continue
                if line is None:
                    res.status, res.error = "no_output", "entry exited without a result"
                    break
                try:
                    msg = json.loads(line)
                    kind = msg["type"]
                except (ValueError, KeyError, TypeError):
                    res.status, res.error = "protocol_error", line[:300]
                    break
                if kind == "final":
                    res.value, res.status = msg.get("value"), "ok"
                    break
                if kind == "crash":
                    res.status, res.error = "crash", msg.get("error")
                    break
                handler = handlers.get(kind)
                if handler is None:
                    ok = reply({"error": f"api.{kind} is not available to the {role}"})
                else:
                    try:
                        ok = reply({"value": handler(msg)})
                    except BudgetError as e:
                        ok = reply({"error": "budget", "detail": str(e)})
                    except (ValueError, TypeError) as e:
                        ok = reply({"error": f"bad request: {e}"[:300]})
                if not ok:
                    res.status, res.error = "crash", "entry closed its pipe"
                    break
        finally:
            kill_group(proc)
            proc.wait()
            for t in threads:
                t.join(timeout=2)
            res.stderr_tail = "".join(err)[-3000:]
            res.wall_s = round(time.monotonic() - start, 2)
    return res
