"""Running agents: the solver on tasks, the improvement procedure on the agent.

All model calls go through here, metered per call into a Ledger, so every
dollar -- including rejected candidates, trials and audits -- is accounted for.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from rsi import policy as rsi_policy

from .broker import BudgetError, run_entry, valid_llm_request
from .grading import check_examples, grade
from .normalize import present
from .tasks import Task

AGENT_FILES = ("solver.py", "improver.py")
ENTRY = {"solver.py": "solve", "improver.py": "improve"}


def check_agent(files: dict[str, str]) -> list[str]:
    out = []
    for name in AGENT_FILES:
        res = rsi_policy.check(files[name], [], entry=ENTRY[name])
        out += [f"{name}: {v}" for v in res["violations"]]
    return out


class Ledger:
    """Thread-safe spend and usage log. Rows: (purpose, role, model, in, out, usd, refused, mismatch)."""

    def __init__(self, on_add=None):
        self.rows: list[dict] = []
        self._lock = threading.Lock()
        self.on_add = on_add

    def add(self, purpose: str, role: str, r) -> None:
        row = {"purpose": purpose, "role": role, "model": r.requested_model,
               "served": r.served_model, "in": r.input_tokens, "out": r.output_tokens,
               "usd": r.cost_usd, "refused": r.refused, "mismatch": r.model_mismatch,
               "category": r.refusal_category}
        with self._lock:
            self.rows.append(row)
        if self.on_add:
            self.on_add(row)

    @property
    def usd(self) -> float:
        return sum(r["usd"] for r in self.rows)

    def summary(self) -> dict:
        out: dict = {}
        for r in self.rows:
            k = f"{r['purpose']}/{r['role']}/{r['model']}"
            s = out.setdefault(k, {"calls": 0, "in": 0, "out": 0, "usd": 0.0, "refused": 0, "mismatch": 0})
            s["calls"] += 1
            s["in"] += r["in"]
            s["out"] += r["out"]
            s["usd"] += r["usd"]
            s["refused"] += int(r["refused"])
            s["mismatch"] += int(r["mismatch"])
        return out


@dataclass
class Meter:
    llm_calls: int
    output_tokens: int
    extra: dict = field(default_factory=dict)   # e.g. checks, trial_tasks remaining
    used_calls: int = 0
    used_out: int = 0
    refusals: int = 0

    def remaining(self) -> dict:
        return {"llm_calls": self.llm_calls - self.used_calls,
                "output_tokens": self.output_tokens - self.used_out, **self.extra}


def _llm_handler(model, meter: Meter, ledger: Ledger, purpose: str, role: str, ctx: dict):
    def handle(msg):
        if meter.used_calls >= meter.llm_calls or meter.used_out >= meter.output_tokens:
            raise BudgetError("model call budget exhausted")
        if not valid_llm_request(msg):
            raise ValueError("plain-text messages only")
        cap = meter.output_tokens - meter.used_out
        req = msg.get("max_tokens")
        max_tokens = min(int(req), cap) if isinstance(req, int) and req > 0 else min(model.max_tokens, cap)
        call_ctx = dict(ctx, role=role, call_index=meter.used_calls)
        meter.used_calls += 1
        if max_tokens < 256:
            raise ValueError(f"max_tokens={max_tokens} is below the 256 minimum")
        try:
            r = model.complete(msg["messages"], system=msg.get("system") or None, max_tokens=max_tokens,
                               context=call_ctx)
        except Exception as e:  # provider rejected the request (e.g. output limit): the agent's problem
            name = type(e).__name__
            if "RateLimit" in name or "Connection" in name or "Timeout" in name or "InternalServer" in name:
                raise
            raise ValueError(f"model call failed: {name}: {str(e)[:200]}")
        meter.used_out += r.output_tokens
        ledger.add(purpose, role, r)
        if r.refused:
            meter.refusals += 1
        if r.model_mismatch:
            raise ValueError("response served by a different model; discarded")
        return r.text
    return handle


# --------------------------------------------------------------------------
# Solver
# --------------------------------------------------------------------------

def run_solver(solver_src: str, task: Task, model, sandbox, cfg: dict, ledger: Ledger,
               purpose: str, nonce: str) -> dict:
    b = cfg["solver_budget"]
    meter = Meter(b["llm_calls"], b["output_tokens"], {"checks": b["checks"]})

    def check(msg):
        if meter.extra["checks"] <= 0:
            raise BudgetError("check budget exhausted")
        if not isinstance(msg.get("code"), str):
            raise ValueError("code must be a string")
        meter.extra["checks"] -= 1
        return check_examples(msg["code"], task.examples, sandbox)

    handlers = {"llm": _llm_handler(model, meter, ledger, purpose, "solver",
                                    {"task_id": task.id, "nonce": nonce}),
                "check": check, "budget": lambda msg: meter.remaining()}
    res = run_entry("solver", solver_src, task.public(), handlers, sandbox, b["wall_seconds"])
    code = res.value if res.status == "ok" and isinstance(res.value, str) else None
    return {"code": code, "status": res.status, "error": res.error, "calls": meter.used_calls,
            "refusals": meter.refusals}


def evaluate(solver_src: str, tasks: list[Task], model, sandbox, cfg: dict, ledger: Ledger,
             purpose: str, nonce: str) -> dict:
    """Score a solver on tasks (hidden tests). Results are safe to show an improver:
    examples are already public; hidden tests are reported only as a pass count."""
    def one(task: Task):
        run = run_solver(solver_src, task, model, sandbox, cfg, ledger, purpose, nonce)
        if run["code"] is None:
            return {"id": task.id, "passed": False, "examples": task.examples,
                    "failure": f"solver {run['status']}", "calls": run["calls"]}
        g = grade(run["code"], task.hidden, sandbox)
        fail = None if g["passed"] else (
            g["failure"] if isinstance(g["failure"], str) else f"{g['n_passed']}/{g['n']} hidden tests passed")
        return {"id": task.id, "passed": g["passed"], "examples": task.examples, "failure": fail,
                "calls": run["calls"]}

    with ThreadPoolExecutor(max_workers=cfg.get("workers", 8)) as pool:
        results = list(pool.map(one, tasks))
    return {"n": len(results), "n_passed": sum(r["passed"] for r in results), "results": results}


# --------------------------------------------------------------------------
# Improvement procedure
# --------------------------------------------------------------------------

def run_improver(files: dict[str, str], ctx: dict, model, presentation: str, sandbox, cfg: dict,
                 trial_tasks: list[Task], ledger: Ledger, purpose: str, nonce: str) -> dict:
    b = cfg["improver_budget"]
    meter = Meter(b["llm_calls"], b["output_tokens"], {"trial_tasks": b["trial_tasks"]})
    presented, reports = {}, {}

    def source(msg):
        name = msg.get("name")
        if name not in AGENT_FILES:
            raise ValueError(f"unknown file {name!r}")
        if name not in presented:
            presented[name], rep = present(files[name], presentation)
            reports[name] = rep.to_dict()
        return presented[name]

    def trial(msg):
        src, n = msg.get("source"), msg.get("n")
        if not isinstance(src, str) or not isinstance(n, int) or n <= 0:
            raise ValueError("trial(source: str, n: int > 0)")
        n = min(n, meter.extra["trial_tasks"], len(trial_tasks))
        if n <= 0:
            raise BudgetError("trial budget exhausted")
        meter.extra["trial_tasks"] -= n
        if rsi_policy.check(src, [], entry="solve")["violations"]:
            return {"solved": 0, "n": n, "error": "policy violation"}
        ev = evaluate(src, trial_tasks[:n], model, sandbox, cfg, ledger, purpose + ":trial", nonce + ":trial")
        return {"solved": ev["n_passed"], "n": n}

    handlers = {"llm": _llm_handler(model, meter, ledger, purpose, "improver", {"nonce": nonce}),
                "source": source, "trial": trial, "budget": lambda msg: meter.remaining()}
    res = run_entry("improver", files["improver.py"], ctx, handlers, sandbox, b["wall_seconds"])
    out = {"status": res.status, "error": res.error, "calls": meter.used_calls, "refusals": meter.refusals,
           "presentation": reports, "files": {}, "note": ""}
    if res.status == "ok" and isinstance(res.value, dict):
        fs = res.value.get("files") or {}
        if isinstance(fs, dict):
            out["files"] = {k: v for k, v in fs.items() if k in AGENT_FILES and isinstance(v, str) and v.strip()}
        note = res.value.get("note")
        out["note"] = note[:500] if isinstance(note, str) else ""
    return out
