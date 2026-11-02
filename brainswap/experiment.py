"""The whole Brain-Swap experiment, end to end.

    1. tasks      disjoint partitions: evo_dev, evo_progress, audit_dev, sealed
    2. baselines  the seed solver on the sealed set under each model
    3. evolution  L self-improving lineages per model (mode=full)
    4. controls   frozen-improver and one-generation lineages per model
    5. audits     forked continuations: seed solver + checkpoint procedure, memory
                  cleared, run under BOTH models x each presentation, scored on sealed
    6. analysis   see analysis.py

Evolution and controls always finish before audits start, and nothing under
audits/ is ever read by an evolving line. Every phase is resumable.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from rsi.config import load_config as load_rsi_config

from .broker import InProcess
from .lineage import BudgetStop, Line
from .models import make_model
from .runtime import AGENT_FILES, Ledger, evaluate
from .tasks import build_partitions, load as load_tasks, save as save_tasks

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = Path(__file__).with_name("seed")


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(path: str | Path) -> dict:
    """YAML config; `extends: other.yaml` deep-merges over another config."""
    p = Path(path)
    if not p.is_absolute() and not p.exists():
        p = Path(__file__).with_name("configs") / p
    cfg = yaml.safe_load(p.read_text())
    if "extends" in cfg:
        base = load_config(p.parent / cfg.pop("extends"))
        base.pop("_path", None)
        # Lists and partition specs replace rather than merge.
        if "tasks" in cfg and "partitions" in cfg["tasks"]:
            base["tasks"]["partitions"] = {}
        cfg = _merge(base, cfg)
    cfg["_path"] = str(p)
    return cfg


def seed_files() -> dict[str, str]:
    return {n: (SEED_DIR / n).read_text() for n in AGENT_FILES}


class Spend:
    """Global spend across every line and every resume, checked before each generation
    and evaluation. Every model call is appended to spend.jsonl as it happens, so
    interrupted work is still counted."""

    def __init__(self, cap: float | None, path: Path, per_model: dict | None = None,
                 model_keys: dict | None = None):
        self.cap, self.path, self._lock = cap, path, threading.Lock()
        self.per_model = per_model or {}          # model key -> cap
        self.model_keys = model_keys or {}        # model id -> key
        self._usd = 0.0
        self.by_key: dict = {}
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    self._tally(json.loads(line))

    def _tally(self, row: dict) -> None:
        self._usd += row.get("usd", 0.0)
        k = self.model_keys.get(row["model"], row["model"])
        self.by_key[k] = self.by_key.get(k, 0.0) + row.get("usd", 0.0)

    def _record(self, row: dict) -> None:
        with self._lock:
            self._tally(row)
            with self.path.open("a") as f:
                f.write(json.dumps(row) + "\n")

    def new(self) -> Ledger:
        return Ledger(on_add=self._record)

    @property
    def usd(self) -> float:
        return self._usd

    def guard(self):
        if self.cap is not None and self.usd >= self.cap:
            raise BudgetStop(f"total spend ${self.usd:.2f} reached the cap ${self.cap:g}")
        for k, cap in self.per_model.items():
            if self.by_key.get(k, 0.0) >= cap:
                raise BudgetStop(f"model {k} spend ${self.by_key[k]:.2f} reached its cap ${cap:g}")


class Experiment:
    def __init__(self, cfg: dict, out: Path, *, mock_scenario: str | None = None, log=print):
        self.cfg, self.out, self.mock, self.log = cfg, out, mock_scenario, log
        self.out.mkdir(parents=True, exist_ok=True)
        self.prices = load_rsi_config()["prices_usd_per_mtok"] | cfg.get("prices_usd_per_mtok", {})
        iso = cfg.get("sandbox", {}).get("isolation", "bwrap")
        if iso == "inprocess" and not mock_scenario:
            raise SystemExit("isolation 'inprocess' is only allowed with mock models.")
        if iso == "inprocess":
            self.sandbox = InProcess()
        else:
            from rsi.sandbox import Sandbox
            self.sandbox = Sandbox(iso, cfg.get("sandbox", {}).get("mem_mb", 1024))
            if not mock_scenario and self.sandbox.isolation != "bwrap":
                raise SystemExit("Real runs need bubblewrap isolation.")
        lim = cfg["limits"]
        bad = [c for c in cfg["audits"]["checkpoints"] if c > cfg["evolution"]["generations"]]
        if bad:
            raise SystemExit(f"audits.checkpoints {bad} exceed evolution.generations={cfg['evolution']['generations']}")
        self.spend = Spend(None if mock_scenario else lim["max_usd_total"], self.out / "spend.jsonl",
                           None if mock_scenario else lim.get("max_usd_per_model"),
                           {spec["model"]: k for k, spec in cfg["models"].items()})
        self.tasks = self._tasks()
        registry = {t.id: t for part in self.tasks.values() for t in part}
        self.models = {k: make_model(spec, self.prices, mock_scenario=mock_scenario, tasks=registry)
                       for k, spec in cfg["models"].items()}
        self.run_cfg = dict(cfg["budgets"], workers=cfg.get("workers", 8))

    # ---- phase 1: tasks ----------------------------------------------------
    def _tasks(self):
        path = self.out / "tasks.json"
        if not path.exists():
            parts = build_partitions(self.cfg["tasks"]["partitions"], self.cfg["tasks"]["seed"])
            save_tasks(parts, path)
        return load_tasks(path)

    def line(self, name, out_dir, model_key, start, dev, **kw) -> Line:
        return Line(name, out_dir, self.models[model_key], self.run_cfg, start, dev,
                    sandbox=self.sandbox, ledger=self.spend.new(), budget_guard=self.spend.guard,
                    require_proc_edit=bool(self.cfg["evolution"].get("require_proc_edit", False)),
                    log=lambda m: None, **kw)

    # ---- phase 2: sealed baselines -----------------------------------------
    def sealed_baselines(self) -> dict:
        path = self.out / "sealed_baselines.json"
        if path.exists():
            return json.loads(path.read_text())
        reps = self.cfg["audits"].get("sealed_baseline_repeats", 2)
        out = {}
        for key in self.models:
            led = self.spend.new()
            scores = [evaluate(seed_files()["solver.py"], self.tasks["sealed"], self.models[key], self.sandbox,
                               self.run_cfg, led, "sealed", f"baseline:{key}:{r}")["n_passed"] for r in range(reps)]
            out[key] = {"scores": scores, "mean": sum(scores) / reps, "n": len(self.tasks["sealed"]),
                        "usd": led.usd}
        path.write_text(json.dumps(out, indent=1))
        return out

    # ---- phases 3-4: evolution and controls ---------------------------------
    def lines_spec(self):
        ev, bl = self.cfg["evolution"], self.cfg.get("baselines", {})
        for key in self.models:
            for l in range(ev["lineages_per_model"]):
                yield ("evolution", f"{key}{l}", key, "full")
            for l in range(bl.get("frozen_lineages_per_model", 0)):
                yield ("frozen", f"{key}{l}", key, "frozen")
            for l in range(bl.get("onegen_lineages_per_model", 0)):
                yield ("onegen", f"{key}{l}", key, "onegen")

    def evolve(self) -> list[dict]:
        G = self.cfg["evolution"]["generations"]

        def go(spec):
            group, name, key, mode = spec
            ln = self.line(f"{group}-{name}", self.out / group / name, key, seed_files(), self.tasks["evo_dev"],
                           progress_tasks=self.tasks["evo_progress"], mode=mode)
            s = ln.run(G)
            self.log(f"{group}/{name}: final dev bar {s['final_bar']:g}, accepted {s['accepted']}, "
                     f"procedure edits kept {s['proc_edits_accepted']}")
            return dict(s, group=group)

        with ThreadPoolExecutor(max_workers=self.cfg.get("parallel_lines", 2)) as pool:
            return list(pool.map(go, list(self.lines_spec())))

    # ---- phase 5: audits ------------------------------------------------------
    def audit_specs(self):
        a = self.cfg["audits"]
        L = self.cfg["evolution"]["lineages_per_model"]
        R = a.get("replicates_per_cell", 1)
        keys = list(self.models)
        for pres in a["presentations"]:
            for op in keys:
                for rep in range(R):
                    # Gen 0: every lineage starts with the same procedure, so gen-0 cells
                    # are replicates; split them into pseudo-origins to estimate the null.
                    for r in range(2 * L):
                        yield {"checkpoint": 0, "origin": keys[r // L], "lineage": r % L, "op": op,
                               "pres": pres, "rep": rep, "procedure_from": None}
                    for ck in a["checkpoints"]:
                        for origin in keys:
                            for l in range(L):
                                yield {"checkpoint": ck, "origin": origin, "lineage": l, "op": op, "pres": pres,
                                       "rep": rep, "procedure_from": f"evolution/{origin}{l}"}

    def audit(self) -> list[dict]:
        a = self.cfg["audits"]
        base = self.sealed_baselines()
        K = a["continuation_generations"]

        def go(spec):
            cid = (f"c{spec['checkpoint']}-{spec['origin']}{spec['lineage']}-op{spec['op']}-{spec['pres']}"
                   + (f"-r{spec['rep']}" if spec["rep"] else ""))
            d = self.out / "audits" / cid
            res_path = d / "result.json"
            if res_path.exists():
                return json.loads(res_path.read_text())
            start = seed_files()   # the ORIGINAL solver, always
            if spec["procedure_from"]:
                ck_dir = self.out / spec["procedure_from"] / "gens" / f"g{spec['checkpoint']:03d}"
                start["improver.py"] = (ck_dir / "improver.py").read_text()
            ln = self.line(cid, d / "line", spec["op"], start, self.tasks["audit_dev"],
                           presentation=spec["pres"], mode="full")
            s = ln.run(K)
            final = ln.files_at(K)
            led = self.spend.new()
            sealed = evaluate(final["solver.py"], self.tasks["sealed"], self.models[spec["op"]], self.sandbox,
                              self.run_cfg, led, "sealed", f"{cid}:sealed")["n_passed"]
            hist = json.loads((d / "line" / "history.json").read_text())
            pres_rows = [r["presentation"].get("improver.py") for r in hist if r.get("presentation")]
            pres_rows = [p for p in pres_rows if p]
            out = dict(spec, cell=cid, sealed=sealed, n_sealed=len(self.tasks["sealed"]),
                       baseline=base[spec["op"]]["mean"], gain=sealed - base[spec["op"]]["mean"],
                       accepted=s["accepted"], proc_edits_accepted=s["proc_edits_accepted"],
                       usd=s["usd"] + led.usd,
                       presentation_coverage=(sum(p["coverage"] for p in pres_rows) / len(pres_rows)
                                              if pres_rows else None),
                       tokens_before=(sum(p["tokens_before"] for p in pres_rows) / len(pres_rows)
                                      if pres_rows else None),
                       tokens_after=(sum(p["tokens_after"] for p in pres_rows) / len(pres_rows)
                                     if pres_rows else None),
                       verified=all(p["verified"] for p in pres_rows))
            res_path.write_text(json.dumps(out, indent=1))
            return out

        specs = list(self.audit_specs())
        with ThreadPoolExecutor(max_workers=self.cfg.get("parallel_lines", 2)) as pool:
            results = list(pool.map(go, specs))
        self.log(f"audits: {len(results)} cells")
        return results

    def run(self) -> dict:
        try:
            self.sealed_baselines()
            lines = self.evolve()
            cells = self.audit()
        except BudgetStop as e:
            self.log(f"STOPPED: {e}")
            raise
        (self.out / "lines.json").write_text(json.dumps(lines, indent=1))
        (self.out / "cells.json").write_text(json.dumps(cells, indent=1))
        return {"lines": lines, "cells": cells, "usd": self.spend.usd}
