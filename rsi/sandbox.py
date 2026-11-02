"""Run untrusted Python and grade its output.

Every piece of model-written code -- the candidate solutions *and* the
scaffolds that produce them -- runs in a child process built here. Nothing
model-written ever executes inside the harness process itself.

Two isolation levels:

* ``bwrap``  -- bubblewrap: no network, a private /tmp, and a read-only view of
  the Python install only. The repo (and therefore the hidden tests) is not
  visible. Use this for every real run. CI installs it.
* ``none``   -- plain subprocess with resource limits. Fine for local mock and
  dev runs; a determined program could read files on disk.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

STDERR_KEEP = 4000  # chars of stderr kept per run


@dataclass
class RunResult:
    stdout: str
    stderr: str
    returncode: int | None
    timed_out: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GradeResult:
    passed: bool
    n_passed: int
    n_total: int
    # kind: "wrong_answer" | "runtime_error" | "timeout" | "no_tests"
    failure: dict | None = None
    # Full run for the first failing test. Callers decide what to expose.
    failure_run: RunResult | None = field(default=None, repr=False)


# --------------------------------------------------------------------------
# Output comparison (mirrors LiveCodeBench's stdin grader, slightly more
# lenient about whitespace inside a line).
# --------------------------------------------------------------------------

def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.strip().split("\n")]


def _tokens_equal(a: str, b: str) -> bool:
    if a == b:
        return True
    try:
        return Decimal(a) == Decimal(b)
    except (InvalidOperation, ValueError):
        return False


def outputs_match(actual: str, expected: str) -> bool:
    got, want = _lines(actual), _lines(expected)
    if len(got) != len(want):
        return False
    for g, w in zip(got, want):
        if g == w:
            continue
        gt, wt = g.split(), w.split()
        if len(gt) != len(wt) or not all(_tokens_equal(x, y) for x, y in zip(gt, wt)):
            return False
    return True


# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------

def bwrap_available() -> bool:
    if not shutil.which("bwrap"):
        return False
    try:
        r = subprocess.run(
            ["bwrap", "--ro-bind", "/", "/", "--unshare-all", "--die-with-parent", "true"],
            capture_output=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


def resolve_isolation(requested: str) -> str:
    """'auto' -> bwrap when it works, otherwise none (with a warning)."""
    if requested == "none":
        return "none"
    if bwrap_available():
        return "bwrap"
    if requested == "bwrap":
        raise RuntimeError(
            "sandbox.isolation is 'bwrap' but bubblewrap is not usable here. "
            "Install it (apt-get install bubblewrap) or set isolation: none for local dev."
        )
    print("[sandbox] WARNING: bubblewrap unavailable; running with isolation=none. "
          "Do not use results from this machine as real data.", file=sys.stderr)
    return "none"


def _python_roots() -> list[str]:
    roots = {sys.base_prefix, sys.prefix, str(Path(os.path.realpath(sys.executable)).parent.parent)}
    return sorted(r for r in roots if r and os.path.isdir(r))


def wrap_command(cmd: list[str], isolation: str, workdir: str,
                 ro_files: dict[str, str] | None = None) -> list[str]:
    """Wrap ``cmd`` so it runs isolated. ``workdir`` is mounted at /work.

    ``ro_files`` maps sandbox path -> host path for extra read-only files.
    """
    if isolation == "none":
        return cmd
    args = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    for d in ("/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc/alternatives"):
        if os.path.exists(d):
            args += ["--ro-bind", d, d]
    for root in _python_roots():
        if not root.startswith("/usr/"):
            args += ["--ro-bind", root, root]
    args += ["--bind", workdir, "/work", "--chdir", "/work"]
    for dest, src in (ro_files or {}).items():
        args += ["--ro-bind", src, dest]
    return args + ["--"] + cmd


_warned_no_prlimit = False


def limit_prefix(mem_mb: int, cpu_s: int) -> list[str]:
    """Resource limits via util-linux ``prlimit``.

    (Not ``preexec_fn``: evaluation is multi-threaded and preexec_fn can
    deadlock in threaded programs.) Missing on macOS -> no limits, warned once.
    """
    global _warned_no_prlimit
    if not shutil.which("prlimit"):
        if not _warned_no_prlimit:
            print("[sandbox] WARNING: prlimit not found; running without memory/CPU limits.",
                  file=sys.stderr)
            _warned_no_prlimit = True
        return []
    return ["prlimit", f"--as={mem_mb * 1024 * 1024}", f"--cpu={cpu_s}",
            f"--fsize={64 * 1024 * 1024}", "--core=0", "--"]


SAFE_ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
            "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
if os.name == "nt":  # best effort for local mock runs on Windows; real runs are Linux-only
    SAFE_ENV = {**SAFE_ENV, "PATH": os.environ.get("PATH", ""),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows")}

# Exit codes meaning "killed for time": SIGXCPU from the CPU rlimit, SIGKILL from us.
_KILLED = {-getattr(signal, n) for n in ("SIGXCPU", "SIGKILL") if hasattr(signal, n)}


def kill_group(proc: subprocess.Popen) -> None:
    try:
        if hasattr(os, "killpg"):
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass


# --------------------------------------------------------------------------
# Sandbox
# --------------------------------------------------------------------------

class Sandbox:
    def __init__(self, isolation: str = "auto", mem_mb: int = 1024,
                 default_timeout_s: float = 10.0):
        self.isolation = resolve_isolation(isolation)
        self.mem_mb = mem_mb
        self.default_timeout_s = default_timeout_s

    def _exec(self, workdir: str, stdin: str, timeout_s: float) -> RunResult:
        script = "main.py" if self.isolation == "none" else "/work/main.py"
        # -I: ignore env/user site; -S: no site-packages -> stdlib only, same everywhere.
        cmd = limit_prefix(self.mem_mb, int(timeout_s) + 1) + wrap_command(
            [sys.executable, "-I", "-S", script], self.isolation, workdir)
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=workdir, env=SAFE_ENV, start_new_session=True,
        )
        try:
            out, err = proc.communicate(stdin.encode("utf-8", "replace"), timeout=timeout_s)
            timed_out = False
        except subprocess.TimeoutExpired:
            kill_group(proc)
            out, err = proc.communicate()
            timed_out = True
        return RunResult(
            stdout=out.decode("utf-8", "replace"),
            stderr=err.decode("utf-8", "replace")[-STDERR_KEEP:],
            returncode=None if timed_out else proc.returncode,
            timed_out=timed_out or proc.returncode in _KILLED,
        )

    def run(self, code: str, stdin: str = "", timeout_s: float | None = None) -> RunResult:
        timeout_s = timeout_s or self.default_timeout_s
        with tempfile.TemporaryDirectory(prefix="rsi-run-") as d:
            Path(d, "main.py").write_text(code)
            return self._exec(d, stdin, timeout_s)

    def grade(self, code: str, tests: list[dict], timeout_s: float | None = None,
              stop_on_fail: bool = True) -> GradeResult:
        if not tests:
            return GradeResult(False, 0, 0, {"kind": "no_tests"})
        timeout_s = timeout_s or self.default_timeout_s
        n_passed, failure, failure_run = 0, None, None
        with tempfile.TemporaryDirectory(prefix="rsi-grade-") as d:
            Path(d, "main.py").write_text(code)
            for i, t in enumerate(tests):
                r = self._exec(d, t["input"], timeout_s)
                if r.timed_out:
                    kind = "timeout"
                elif r.returncode != 0:
                    kind = "runtime_error"
                elif not outputs_match(r.stdout, t["output"]):
                    kind = "wrong_answer"
                else:
                    n_passed += 1
                    continue
                if failure is None:
                    failure, failure_run = {"kind": kind, "test_index": i}, r
                if stop_on_fail:
                    break
        return GradeResult(n_passed == len(tests), n_passed, len(tests), failure, failure_run)
