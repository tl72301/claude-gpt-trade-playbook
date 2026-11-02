"""Estimands, uncertainty, and the interpretation rules.

Notation: g(o, l, x) = sealed-set gain of a continuation run by operating model
x, starting from the seed solver and the procedure of lineage l evolved by
origin o, relative to the seed solver's own sealed score under x.

Lineages are the unit of replication (tasks within a lineage are not
independent). Everything is computed from one number per lineage:

  d(o, l)      = g(o, l, A) - g(o, l, B)            how much better A runs that procedure
  S            = (mean_l d(A, l) - mean_l d(B, l)) / 2
               = (H_A + H_B) / 2, with H_x = mean g(x, ., x) - mean g(other, ., x)
  dS           = S(checkpoint) - S(gen 0)            gen 0: identical procedures, so S(0) ~ 0
  P_x          = mean g(., ., x) at checkpoint - mean at gen 0     portable gain for operator x
  pres. effect = dS(orig) - dS(pres), paired by lineage              did the presentation change it?

Intervals: Welch t-intervals over lineages (Satterthwaite df). With 3 lineages
per origin they are wide; that is the honest answer. (A percentile bootstrap
was tried and rejected: with so few lineages it is anti-conservative and
produced false positives in the null simulation.) A logit-scale S is reported
too, because gains near the ceiling or floor are compressed.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

# Two-sided 95% t critical values, df 1..30; normal beyond.
_T975 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160,
         2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056,
         2.052, 2.048, 2.045, 2.042]


def t975(df: float) -> float:
    if not df == df or df < 1:
        return float("inf")
    if df >= 30:
        return 1.96 + (2.042 - 1.96) * 30 / df
    lo = int(df)
    frac = df - lo
    a, b = _T975[lo - 1], _T975[min(lo, 29)]
    return a + (b - a) * frac


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def _var(xs):
    xs = list(xs)
    if len(xs) < 2:
        return float("nan")
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


class Est:
    """A linear combination sum_i c_i * mean(sample_i) of independent samples."""

    def __init__(self, terms):
        self.terms = [(c, list(xs)) for c, xs in terms if xs]

    @property
    def value(self):
        return sum(c * _mean(xs) for c, xs in self.terms)

    def ci(self):
        parts = [(c * c * _var(xs) / len(xs), len(xs) - 1) for c, xs in self.terms]
        v = sum(p for p, _ in parts)
        if not v == v:
            return None
        if v == 0:
            return [self.value, self.value]
        df = v * v / sum(p * p / max(df, 1) for p, df in parts if p > 0)
        h = t975(df) * math.sqrt(v)
        return [self.value - h, self.value + h]


def _logit_gain(sealed, base, n):
    def lg(k):
        p = (k + 0.5) / (n + 1)
        return math.log(p / (1 - p))
    return lg(sealed) - lg(base)


def _per_lineage(cells, ops, key="gain"):
    """(checkpoint, pres) -> origin -> {lineage: {op: value}}; continuation replicates are averaged."""
    acc = defaultdict(list)
    for c in cells:
        acc[(c["checkpoint"], c["pres"], c["origin"], c["lineage"], c["op"])].append(c[key])
    idx = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for (ck, pres, o, l, op), vals in acc.items():
        idx[(ck, pres)][o][l][op] = _mean(vals)
    return idx


def _d(group, origin, ops):
    a, b = ops
    return {l: v[a] - v[b] for l, v in group.get(origin, {}).items() if a in v and b in v}


def _gx(group, x):
    return [v[x] for lineages in group.values() for v in lineages.values() if x in v]


def analyze(cells: list[dict], ops: list[str]) -> dict:
    for c in cells:
        c["logit_gain"] = _logit_gain(c["sealed"], c["baseline"], c["n_sealed"])
    idx = _per_lineage(cells, ops)
    idx_logit = _per_lineage(cells, ops, "logit_gain")
    a, b = ops
    checkpoints = sorted({k[0] for k in idx})
    order = ["orig", "fmt", "norm", "neutral", "nocomment"]
    presentations = sorted({k[1] for k in idx}, key=order.index)

    def S_est(group):
        return Est([(0.5, _d(group, a, ops).values()), (-0.5, _d(group, b, ops).values())])

    rows = []
    for pres in presentations:
        g0 = idx[(0, pres)]
        for ck in checkpoints:
            g = idx[(ck, pres)]
            S = S_est(g)
            H = {a: _mean(v[a] for v in g[a].values() if a in v) - _mean(v[a] for v in g[b].values() if a in v),
                 b: _mean(v[b] for v in g[b].values() if b in v) - _mean(v[b] for v in g[a].values() if b in v)}
            matrix = {f"{o}->{x}": _mean(v[x] for v in g[o].values() if x in v) for o in ops for x in ops}
            r = {"checkpoint": ck, "pres": pres, "S": S.value, "S_ci": S.ci(), "H": H, "matrix": matrix,
                 "S_logit": S_est(idx_logit[(ck, pres)]).value,
                 "n_lineages": {o: len(g[o]) for o in ops}}
            if ck > 0:
                dS = Est(S_est(g).terms + [(-c, xs) for c, xs in S_est(g0).terms])
                r["dS"], r["dS_ci"] = dS.value, dS.ci()
                r["portable"], r["portable_ci"] = {}, {}
                for x in ops:
                    P = Est([(1.0, _gx(g, x)), (-1.0, _gx(g0, x))])
                    r["portable"][x], r["portable_ci"][x] = P.value, P.ci()
                if pres != "orig" and (ck, "orig") in idx:
                    go, g0o = idx[(ck, "orig")], idx[(0, "orig")]
                    terms = []
                    for grp, grp_p, sign in ((go, g, 1.0), (g0o, g0, -1.0)):
                        for origin, c in ((a, 0.5), (b, -0.5)):
                            do, dp = _d(grp, origin, ops), _d(grp_p, origin, ops)
                            paired = [do[l] - dp[l] for l in do if l in dp]
                            terms.append((sign * c, paired))
                    E = Est(terms)
                    r["pres_effect"], r["pres_effect_ci"] = E.value, E.ci()
            rows.append(r)

    pres_info = {}
    for pres in presentations:
        cs = [c for c in cells if c["pres"] == pres and c.get("tokens_before")]
        pres_info[pres] = {
            "tokens_before": _mean(c["tokens_before"] for c in cs),
            "tokens_after": _mean(c["tokens_after"] for c in cs),
            "coverage": _mean(c["presentation_coverage"] for c in cs if c.get("presentation_coverage") is not None),
            "all_verified": all(c.get("verified", True) for c in cs),
            "mean_gain": _mean(c["gain"] for c in cells if c["pres"] == pres and c["checkpoint"] > 0),
        }
    return {"ops": ops, "checkpoints": checkpoints, "presentations": presentations, "rows": rows,
            "presentation_info": pres_info, "n_cells": len(cells),
            **({"usd_audits": sum(c["usd"] for c in cells)} if cells and all("usd" in c for c in cells) else {})}


def lineage_summary(out_dir: Path) -> dict:
    """Progress-set curves and the RSI-vs-baselines comparison."""
    groups = {}
    for group in ("evolution", "frozen", "onegen"):
        for d in sorted((out_dir / group).glob("*")) if (out_dir / group).exists() else []:
            if not (d / "summary.json").exists():
                continue
            hist = json.loads((d / "history.json").read_text())
            summ = json.loads((d / "summary.json").read_text())
            prog, cur = [], hist[0].get("progress")
            for r in hist:
                if r.get("progress") is not None:
                    cur = r["progress"]
                prog.append(cur)
            groups.setdefault(group, []).append({
                "name": d.name, "model": d.name[0], "bar": [r["bar"] for r in hist], "progress": prog,
                "statuses": [r.get("status") for r in hist[1:]],
                "proc_edits_accepted": summ["proc_edits_accepted"], "accepted": summ["accepted"],
                **({"usd": summ["usd"]} if "usd" in summ else {})})
    comparison = {}
    for group, lines in groups.items():
        for m in sorted({l["model"] for l in lines}):
            gains = [l["progress"][-1] - l["progress"][0] for l in lines if l["model"] == m]
            comparison.setdefault(m, {})[group] = {"progress_gain": _mean(gains), "gains": gains, "n": len(gains)}
    for m, comp in comparison.items():
        if "evolution" in comp and "frozen" in comp:
            E = Est([(1.0, comp["evolution"]["gains"]), (-1.0, comp["frozen"]["gains"])])
            comp["full_minus_frozen"] = {"value": E.value, "ci": E.ci()}
    return {"lines": groups, "comparison": comparison}


def _fmt_ci(c):
    return "n/a" if c is None else f"{c[0]:+.1f}..{c[1]:+.1f}"


def interpret(result: dict, lines: dict) -> list[str]:
    """Plain-language verdicts, following DESIGN_BRAIN_SWAP.md section 8."""
    out = []

    def excl0(c):
        return c is not None and (c[0] > 0 or c[1] < 0)

    for r in result["rows"]:
        if r["checkpoint"] == 0 or r["pres"] != "orig":
            continue
        tag = f"checkpoint {r['checkpoint']}"
        if excl0(r["dS_ci"]) and r["dS"] > 0:
            out.append(f"{tag}: home advantage grew (dS={r['dS']:+.1f} tasks, 95% CI {_fmt_ci(r['dS_ci'])}) "
                       "-> suggests specialization.")
        else:
            out.append(f"{tag}: no reliable growth in home advantage (dS={r['dS']:+.1f}, CI {_fmt_ci(r['dS_ci'])}).")
        for x, v in r["portable"].items():
            if excl0(r["portable_ci"][x]) and v > 0:
                out.append(f"{tag}: evolved procedures beat the seed procedure for operator {x} "
                           f"(+{v:.1f}, CI {_fmt_ci(r['portable_ci'][x])}) -> portable gains.")
    for r in result["rows"]:
        if r["checkpoint"] > 0 and r["pres"] != "orig" and r.get("pres_effect") is not None:
            c = r["pres_effect_ci"]
            if excl0(c):
                word = "REDUCED" if r["pres_effect"] > 0 else "INCREASED"
                out.append(f"checkpoint {r['checkpoint']}: the '{r['pres']}' presentation {word} specialization "
                           f"growth by {abs(r['pres_effect']):.1f} tasks (CI {_fmt_ci(c)}).")
            else:
                out.append(f"checkpoint {r['checkpoint']}: no detectable effect of the '{r['pres']}' presentation "
                           f"on specialization growth ({r['pres_effect']:+.1f}, CI {_fmt_ci(c)}).")
    for m, comp in lines.get("comparison", {}).items():
        fm = comp.get("full_minus_frozen")
        if fm:
            if excl0(fm["ci"]) and fm["value"] > 0:
                out.append(f"model {m}: self-modifying lineages beat the frozen-improver baseline "
                           f"({fm['value']:+.1f} progress tasks, CI {_fmt_ci(fm['ci'])}).")
            else:
                out.append(f"model {m}: self-modifying lineages did NOT reliably beat the frozen-improver baseline "
                           f"({fm['value']:+.1f}, CI {_fmt_ci(fm['ci'])}) -> RSI mechanism not demonstrated.")
    return out
