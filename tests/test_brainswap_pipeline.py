"""End-to-end with SIMULATED models at CI scale, plus the audit-isolation guarantees."""

import hashlib
import json

from brainswap.experiment import Experiment, load_config, seed_files
from brainswap.analysis import analyze, lineage_summary, interpret, Est


def _tree_hash(d):
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(d)).encode() + p.read_bytes())
    return h.hexdigest()


def test_pipeline_and_audit_isolation(tmp_path):
    cfg = load_config("ci.yaml")
    exp = Experiment(cfg, tmp_path, mock_scenario="presentation", log=lambda *_: None)
    exp.sealed_baselines()
    exp.evolve()
    before = _tree_hash(tmp_path / "evolution")
    cells = exp.audit()
    # Audits never write into (or change) evolution.
    assert _tree_hash(tmp_path / "evolution") == before
    seed = seed_files()
    for c in cells:
        g0 = tmp_path / "audits" / c["cell"] / "line" / "gens" / "g000"
        # The original solver is always restored...
        assert (g0 / "solver.py").read_text() == seed["solver.py"]
        # ...and the procedure comes from the stated checkpoint (or the seed at gen 0).
        want = seed["improver.py"] if c["checkpoint"] == 0 else (
            tmp_path / c["procedure_from"] / "gens" / f"g{c['checkpoint']:03d}" / "improver.py").read_text()
        assert (g0 / "improver.py").read_text() == want
    # Crossed design: every (checkpoint, origin, lineage, pres) has both operators.
    keys = {}
    for c in cells:
        keys.setdefault((c["checkpoint"], c["origin"], c["lineage"], c["pres"]), set()).add(c["op"])
    assert all(v == {"A", "B"} for v in keys.values())
    # Frozen lineages never change the procedure.
    for d in (tmp_path / "frozen").glob("*/gens/*"):
        assert (d / "improver.py").read_text() == seed["improver.py"]
    res = analyze(cells, ["A", "B"])
    assert {r["pres"] for r in res["rows"]} == {"orig", "norm"}
    assert interpret(res, lineage_summary(tmp_path))
    # Every model call was logged for cost accounting.
    assert (tmp_path / "spend.jsonl").read_text().count("\n") > 100


def test_inprocess_refused_for_real_models(tmp_path):
    cfg = load_config("ci.yaml")
    try:
        Experiment(cfg, tmp_path, mock_scenario=None)
    except SystemExit as e:
        assert "only allowed with mock" in str(e)
    else:
        raise AssertionError("in-process isolation must be refused for real models")


def test_welch_interval():
    e = Est([(1.0, [1, 2, 3]), (-1.0, [0, 0, 0])])
    lo, hi = e.ci()
    assert e.value == 2 and lo < 2 < hi and hi - lo > 4      # df=2 -> t=4.3, wide


def test_specialization_recovered_on_synthetic_cells():
    cells = []
    for ck in (0, 5):
        for o in "AB":
            for l in range(4):
                for x in "AB":
                    home = 4 if (ck == 5 and o == x) else 0
                    g = 2 + home + (l % 2) * 0.5
                    cells.append({"checkpoint": ck, "pres": "orig", "origin": o, "lineage": l, "op": x,
                                  "gain": g, "sealed": 10 + g, "baseline": 10, "n_sealed": 40, "usd": 0})
    row = [r for r in analyze(cells, ["A", "B"])["rows"] if r["checkpoint"] == 5][0]
    assert abs(row["dS"] - 4) < 1e-9 and row["dS_ci"][0] > 0


def test_budget_accepts_observed_profile(tmp_path):
    import json
    from brainswap.budget import calibrated
    (tmp_path / "spend.jsonl").write_text(json.dumps(
        {"purpose": "dev", "role": "solver", "model": "mock-snake", "in": 100, "out": 50, "usd": 0.0}) + "\n")
    cfg = load_config("ci.yaml")
    prices = {"claude-haiku-5-5": {"input": 1, "output": 1}, "gpt-6.1-terra": {"input": 1, "output": 1},
              "default": {"input": 1, "output": 1}}
    est = calibrated(tmp_path, cfg, prices, {("A", "solver"): 4000.0})
    assert est["by_line"][0]["avg_out"] == 4000


def test_provider_error_becomes_agent_error():
    from brainswap.runtime import _llm_handler, Meter, Ledger

    class Boom:
        max_tokens = 1000
        def complete(self, *a, **k):
            class BadRequestError(Exception): pass
            raise BadRequestError("output limit reached")
    h = _llm_handler(Boom(), Meter(5, 10000), Ledger(), "t", "solver", {})
    import pytest
    with pytest.raises(ValueError, match="model call failed"):
        h({"messages": [{"role": "user", "content": "hi"}]})
    with pytest.raises(ValueError, match="minimum"):
        h({"messages": [{"role": "user", "content": "hi"}], "max_tokens": 10})
