"""SIMULATED models for offline runs. Nothing produced with these is evidence.

Two mock "families" stand in for models A and B. They exist to exercise the
whole pipeline -- evolution, forked audits, the crossed matrix, presentation
conditions, analysis -- and to check that the analysis recovers effects that
were deliberately built in (parameter recovery), and finds none when none were.

How the simulation works
* Solver calls succeed with a probability set by the model's skill, task
  depth, helpful hints in the prompt, and retry feedback. Success returns the
  task's reference program; failure returns a subtly wrong one. Grading is real.
* Improver calls read the presented source and propose edits: flip USE_CHECK,
  raise ATTEMPTS, add hints (solver); raise CANDIDATES / TRIAL_TASKS, add strategy
  notes (procedure). Edit quality q depends on the scenario:
    style      familiarity with the identifier style of the presented procedure
               source (snake_case for A, camelCase for B). Normalization removes it.
    notes      strategy notes written in the model's own dialect help it more
               than notes written by the other model. Normalization keeps them.
    length     a small penalty for longer presented source.
* When a mock rewrites a file it also renames a few locals into its own style,
  so evolved source drifts toward the evolving model's style -- the mechanism
  the presentation intervention targets.
"""

from __future__ import annotations

import ast
import hashlib
import math
import re

from rsi.llm import LLMResult, price_entry, request_cost

from .normalize import rename, style_mix, style_of, token_count

GOOD_HINTS = [
    "Apply the operations in order; intermediate lists may shrink.",
    "Check whether the order of elements changes (sorting, reversing, rotating).",
    "Compare lengths of input and output to spot filtering or slicing.",
    "Look for per-element arithmetic such as adding a constant or a modulus.",
    "Running totals or running maxima often explain growing outputs.",
]
BAD_HINTS = [
    "The answer is usually a single built-in call.",
    "Ignore duplicates in the input.",
]
NOTE_TEXT = [
    "turn each failed task into a concrete hint",
    "prefer edits that add verification over edits that add text",
    "trial several candidates before choosing one",
    "keep the solver prompt short and specific",
]
SCENARIOS = {
    # s_style: weight on identifier-style familiarity of the presented procedure
    # s_home / s_away: effect of each strategy note written by the operating model / by the other
    # s_len: penalty per +100% presented-source length vs. the seed
    # The non-null effects are deliberately LARGE so the demo can show what a detection
    # looks like. Real effects are unknown and may be far smaller.
    "null":         {"s_style": 0.0, "s_home": 0.25, "s_away": 0.25, "s_len": 0.0},
    "presentation": {"s_style": 3.0, "s_home": 0.25, "s_away": 0.25, "s_len": 0.4},
    "content":      {"s_style": 0.0, "s_home": 0.8, "s_away": -0.4, "s_len": 0.0},
}
PROFILES = {
    "snake": {"solve_skill": 0.3, "improve_skill": -0.2},
    "camel": {"solve_skill": -0.1, "improve_skill": -0.3},
}
SEED_PROCEDURE_TOKENS = 1282


def unit(*parts) -> float:
    h = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _section(text: str, name: str) -> str:
    m = re.search(rf"^=== FILE {re.escape(name)} ===\n(.*?)\n^=== END FILE ===$", text, re.DOTALL | re.MULTILINE)
    return m.group(1) if m else ""


def _assign_value(src: str, name: str):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


def _set_assign(src: str, name: str, value) -> str:
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            lines[node.lineno - 1:node.end_lineno] = [f"{name} = {value!r}\n"]
            return "".join(lines)
    return src


def _restyle(src: str, style: str, rng_key: str, k: int) -> str:
    """Rename up to k function locals into ``style`` (the model's dialect)."""
    suffix = ["val", "text", "items", "out", "res"]

    def plan(qualname, names, taken):
        mapping = {}
        cands = [n for n in names if style_of(n) != style]
        ranked = sorted(cands, key=lambda n: unit(rng_key, qualname, n))
        for n in ranked[:k]:
            base = re.sub(r"[A-Z]", lambda m: "_" + m.group(0).lower(), n).strip("_")
            parts = [p for p in base.split("_") if p]
            if len(parts) < 2:
                parts.append(suffix[int(unit(rng_key, n) * len(suffix))])
            new = "_".join(parts) if style == "snake" else parts[0] + "".join(p.title() for p in parts[1:])
            if new not in taken and new not in mapping.values():
                mapping[n] = new
        return mapping

    out, rep = rename(src, plan, "restyle")
    return out if rep.verified else src


class MockModel:
    """Deterministic simulated LLM. ``style`` is 'snake' (model A) or 'camel' (model B)."""

    def __init__(self, name: str, style: str, scenario: str, tasks: dict, prices: dict,
                 priced_as: str, max_tokens: int = 16000):
        self.model = name
        self.style = style
        self.other = "camel" if style == "snake" else "snake"
        self.prof = PROFILES[style]
        self.sc = SCENARIOS[scenario]
        self.tasks = tasks
        self.max_tokens = max_tokens
        self.price = price_entry(priced_as, prices)

    def _result(self, text: str, messages, system, thinking: int) -> LLMResult:
        n_in = (sum(len(m["content"]) if isinstance(m["content"], str) else 0 for m in messages)
                + len(system or "")) // 4
        n_out = len(text) // 4 + thinking
        return LLMResult(text=text, requested_model=self.model, served_model=self.model,
                         stop_reason="end_turn", input_tokens=n_in, output_tokens=n_out,
                         cost_usd=request_cost(self.price, n_in, n_out))

    def complete(self, messages, system=None, max_tokens=None, context=None) -> LLMResult:
        ctx = context or {}
        prompt = messages[-1]["content"] if isinstance(messages[-1]["content"], str) else ""
        if ctx.get("role") == "improver":
            return self._improve(prompt, messages, system, ctx)
        return self._solve(prompt, messages, system, ctx)

    # ---- solver ---------------------------------------------------------------
    def _solve(self, prompt, messages, system, ctx):
        task = self.tasks.get(ctx.get("task_id"))
        if task is None:
            return self._result("```python\ndef f(xs):\n    return xs\n```", messages, system, 200)
        good = sum(h in prompt for h in GOOD_HINTS)
        bad = sum(h in prompt for h in BAD_HINTS)
        feedback = 0.6 if "was wrong" in prompt else 0.0
        z = (self.prof["solve_skill"] + 0.6 - 0.9 * (task.depth - 2)
             + 0.35 * min(good, 3) - 0.3 * bad + feedback)
        draw = unit("solve", self.model, task.id, ctx.get("nonce"), ctx.get("call_index"), len(prompt))
        if draw < sigmoid(z):
            code = task.reference
        else:
            lines = task.reference.splitlines()
            drop = 1 + int(unit("wrong", task.id, draw) * (len(lines) - 2))
            code = "\n".join(lines[:drop] + lines[drop + 1:]) + "\n"
        return self._result(f"```python\n{code}```", messages, system, 300)

    # ---- improver -------------------------------------------------------------
    def _improve(self, prompt, messages, system, ctx):
        solver = _section(prompt, "solver.py")
        proc = _section(prompt, "improver.py")
        if not solver or not proc:
            return self._result("<note>(simulated) could not find the sources</note>", messages, system, 400)
        mix = style_mix(proc)
        familiarity = mix[self.style] - mix[self.other]
        notes = _assign_value(proc, "NOTES") or []
        home = sum(1 for n in notes if n.startswith(f"[{self.style}]"))
        away = sum(1 for n in notes if n.startswith(f"[{self.other}]"))
        length = token_count(proc) / SEED_PROCEDURE_TOKENS - 1
        sc = self.sc
        z = (self.prof["improve_skill"] + sc["s_style"] * familiarity + sc["s_home"] * min(home, 3)
             + sc["s_away"] * min(away, 3) - sc["s_len"] * max(0.0, length))
        q = sigmoid(z)
        key = (self.model, ctx.get("nonce"), ctx.get("call_index"))
        good = unit("q", *key) < q

        # Solver edit.
        attempts = _assign_value(solver, "ATTEMPTS") or 1
        use_check = bool(_assign_value(solver, "USE_CHECK"))
        hints = list(_assign_value(solver, "HINTS") or [])
        new_solver, what = solver, ""
        if good:
            missing = [h for h in GOOD_HINTS if h not in hints]
            options = []
            if not use_check:
                options.append(("VERIFY", None, "verify against the examples and retry"))
            if use_check and attempts < 4:
                options.append(("ATTEMPTS", attempts + 1, "one more attempt"))
            if missing and len([h for h in hints if h in GOOD_HINTS]) < 4:
                options.append(("HINTS", hints + [missing[0]], "add a hint"))
            if options:
                name, value, what = options[int(unit("opt", *key) * len(options))]
                if name == "VERIFY":   # a real model would make both edits at once
                    new_solver = _set_assign(_set_assign(solver, "USE_CHECK", True), "ATTEMPTS", max(2, attempts))
                else:
                    new_solver = _set_assign(solver, name, value)
        else:
            choice = int(unit("bad", *key) * 3)
            if choice == 0 and attempts > 1:
                new_solver, what = _set_assign(solver, "ATTEMPTS", attempts - 1), "fewer attempts"
            elif choice == 1:
                extra = [h for h in BAD_HINTS if h not in hints][:1]
                new_solver, what = _set_assign(solver, "HINTS", hints + extra), "add a (bad) hint"
            else:
                what = "cosmetic rewrite"
        if unit("drift-s", *key) < 0.5:
            new_solver = _restyle(new_solver, self.style, f"s{key}", 1 + int(unit("k", *key) * 2))

        # Procedure (self) edit.
        files = {"solver.py": new_solver}
        if True:   # every proposal carries an improver.py (structural edit 40% of the time, else a restyle)
            structural = unit("meta", *key) < 0.4
            cand = _assign_value(proc, "CANDIDATES") or 1
            trial = _assign_value(proc, "TRIAL_TASKS") or 0
            new_proc = proc
            pick = int(unit("metapick", *key) * 3) if structural else -1
            if pick == 0 and cand < 3:
                new_proc = _set_assign(new_proc, "CANDIDATES", cand + 1)
                if trial == 0:
                    new_proc = _set_assign(new_proc, "TRIAL_TASKS", 4)
            elif pick == 1 and len(notes) < 5:
                text = NOTE_TEXT[int(unit("note", *key) * len(NOTE_TEXT))]
                new_proc = _set_assign(new_proc, "NOTES", notes + [f"[{self.style}] {text}"])
            elif pick == 2 and not good and cand > 1:
                new_proc = _set_assign(new_proc, "CANDIDATES", cand - 1)
            if unit("drift-p", *key) < 0.6 or new_proc == proc:
                new_proc = _restyle(new_proc, self.style, f"p{key}", 1 + int(unit("kp", *key) * 3))
            if new_proc == proc:   # nothing left to restyle: touch a comment so the rule is met
                new_proc = proc.rstrip("\n") + f"\n# gen {ctx.get('generation')} ({self.style})\n"
            files["improver.py"] = new_proc
        body = "".join(f'<file name="{n}">\n{src.rstrip()}\n</file>\n' for n, src in files.items())
        return self._result(f"{body}<note>(simulated {self.style}) {what}</note>", messages, system, 1200)
