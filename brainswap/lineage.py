"""One self-improvement line: an evolution lineage, a baseline, or an audit continuation.

Modes
  full    the procedure may rewrite solver.py and improver.py; an accepted
          improver.py governs every later generation (the RSI condition)
  frozen  improver.py edits are discarded: an unchanged procedure repeatedly
          improves the solver (frozen-improver baseline)
  onegen  every proposal comes from the starting agent with its starting
          results and no memory; the best one is kept (one-generation baseline:
          the same number of proposals, no chaining)

Acceptance is enforced here, outside the agent: the candidate's solver must
solve more development tasks than the current bar, and still beat it on the
mean of a second evaluation. Procedure edits ride along with an accepted solver
gain (they are never accepted alone) -- see DESIGN_BRAIN_SWAP.md, section 4.
With require_proc_edit (v2), a proposal that leaves improver.py unchanged is
discarded before evaluation: the first scout showed models never touch it
unless required.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .runtime import AGENT_FILES, Ledger, check_agent, evaluate, run_improver
from .tasks import Task

MEMORY_CHARS = 2000


class BudgetStop(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    tmp.replace(path)


class Line:
    def __init__(self, name: str, out_dir: Path, model, cfg: dict, start_files: dict[str, str],
                 dev_tasks: list[Task], *, progress_tasks: list[Task] | None = None,
                 presentation: str = "orig", mode: str = "full", require_proc_edit: bool = False, sandbox=None,
                 ledger: Ledger | None = None, budget_guard=None, log=print):
        assert mode in ("full", "frozen", "onegen")
        self.name, self.dir, self.model, self.cfg = name, out_dir, model, cfg
        self.start = dict(start_files)
        self.dev, self.progress = dev_tasks, progress_tasks
        self.presentation, self.mode = presentation, mode
        self.require_proc_edit = require_proc_edit and mode == "full"
        self.sandbox, self.ledger = sandbox, ledger or Ledger()
        self.guard = budget_guard or (lambda: None)
        self.log = log

    # ---- persistence -------------------------------------------------------
    def _gen_dir(self, g: int) -> Path:
        return self.dir / "gens" / f"g{g:03d}"

    def snapshot(self, g: int, files: dict[str, str]) -> None:
        d = self._gen_dir(g)
        d.mkdir(parents=True, exist_ok=True)
        for n in AGENT_FILES:
            (d / n).write_text(files[n])

    def files_at(self, g: int) -> dict[str, str]:
        """The agent in charge after generation g (a checkpoint)."""
        d = self._gen_dir(g)
        return {n: (d / n).read_text() for n in AGENT_FILES}

    def _eval(self, files, tasks, purpose, nonce):
        self.guard()
        return evaluate(files["solver.py"], tasks, self.model, self.sandbox, self.cfg, self.ledger,
                        purpose, f"{self.name}:{nonce}")

    # ---- run ----------------------------------------------------------------
    def run(self, generations: int) -> dict:
        if (self.dir / "summary.json").exists():
            return json.loads((self.dir / "summary.json").read_text())
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True)
        reps = max(1, int(self.cfg.get("seed_repeats", 2)))
        evs = [self._eval(self.start, self.dev, "dev", f"g0:{r}") for r in range(reps)]
        bar = sum(e["n_passed"] for e in evs) / reps
        start_results = evs[0]["results"]
        cur, cur_results = dict(self.start), start_results
        memory = ""
        prog0 = self._eval(cur, self.progress, "progress", "g0:prog")["n_passed"] if self.progress else None
        self.snapshot(0, cur)
        history = [{"generation": 0, "status": "start", "dev": [e["n_passed"] for e in evs], "bar": bar,
                    "progress": prog0, "usd": round(self.ledger.usd, 6)}]
        for g in range(1, generations + 1):
            base_files = self.start if self.mode == "onegen" else cur
            base_results = start_results if self.mode == "onegen" else cur_results
            ctx = {"generation": g, "results": base_results,
                   "memory": "" if self.mode == "onegen" else memory[-MEMORY_CHARS:],
                   "budget": self.cfg["improver_budget"]}
            self.guard()
            prop = run_improver(base_files, ctx, self.model, self.presentation, self.sandbox, self.cfg,
                                self.dev, self.ledger, "improver", f"{self.name}:g{g}")
            cand = dict(base_files, **prop["files"])
            proc_edit = cand["improver.py"] != base_files["improver.py"]
            if self.mode == "frozen" and proc_edit:
                cand["improver.py"] = base_files["improver.py"]
            row = {"generation": g, "proc_edit_proposed": proc_edit,
                   "solver_edit": cand["solver.py"] != base_files["solver.py"],
                   "improver_status": prop["status"], "refusals": prop["refusals"],
                   "presentation": prop["presentation"], "note": prop["note"]}
            if prop["status"] != "ok":
                row["status"], row["error"] = "improver_" + prop["status"], (prop["error"] or "")[-500:]
            elif not row["solver_edit"]:
                row["status"] = "no_solver_change"
            elif self.require_proc_edit and not proc_edit:
                row["status"] = "no_proc_change"      # v2 rule: the procedure must change every round
            elif violations := check_agent(cand):
                row["status"], row["violations"] = "policy_violation", violations[:5]
            else:
                ev = self._eval(cand, self.dev, "dev", f"g{g}:0")
                row["dev"] = [ev["n_passed"]]
                if ev["n_passed"] <= bar:
                    row["status"] = "rejected"
                else:
                    ev2 = self._eval(cand, self.dev, "dev", f"g{g}:1")
                    row["dev"].append(ev2["n_passed"])
                    mean = (ev["n_passed"] + ev2["n_passed"]) / 2
                    if mean <= bar:
                        row["status"] = "rejected_confirmation"
                    else:
                        row["status"] = "accepted"
                        row["proc_edit_accepted"] = cand["improver.py"] != cur["improver.py"]
                        cur, cur_results, bar = cand, ev["results"], mean
                        if self.progress:
                            row["progress"] = self._eval(cur, self.progress, "progress", f"g{g}:prog")["n_passed"]
            if self.mode != "onegen" and prop["note"]:
                memory += f"\ngen {g} ({row['status']}): {prop['note']}"
            row["bar"] = bar
            row["usd"] = round(self.ledger.usd, 6)
            history.append(row)
            self.snapshot(g, cur)
            _write(self.dir / "history.json", history)
            self.log(f"  [{self.name}] g{g} {row['status']} bar={bar:g}")
        summary = {"name": self.name, "model": self.model.model, "mode": self.mode,
                   "presentation": self.presentation, "generations": generations,
                   "final_bar": bar, "accepted": sum(r.get("status") == "accepted" for r in history),
                   "proc_edits_accepted": sum(bool(r.get("proc_edit_accepted")) for r in history),
                   "usd": round(self.ledger.usd, 6), "finished_at": _now()}
        _write(self.dir / "history.json", history)
        _write(self.dir / "ledger.json", self.ledger.summary())
        _write(self.dir / "summary.json", summary)
        return summary
