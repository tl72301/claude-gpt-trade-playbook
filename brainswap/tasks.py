"""Task domain: list-function induction (programming by example).

Each task is a hidden composition of 2-4 list operations, e.g.
    xs -> [x + 3 for x in xs] -> sorted -> drop first 2
The solver sees a handful of input/output examples and must write
``def f(xs): ...`` that reproduces the hidden function. It is graded on 30
hidden inputs (edge cases included) by running the program.

Why this domain
* Cheap: prompts are a few hundred tokens; grading is one sandboxed process.
* Deterministic and executable: correctness is exact list equality.
* Tunable: composition depth sets difficulty, so neither model has to saturate.
* Fresh: tasks are generated from seeds, so every partition (evolution dev,
  audit dev, sealed) is disjoint and new to both models -- no contamination.
* Identifiable: a task is kept only if no other program from a large
  alternative set fits the shown examples but disagrees on hidden inputs.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import random
from dataclasses import dataclass
from pathlib import Path

# (name, params, statement-level python, fn). Statements transform `xs`.
OPS: list[tuple[str, tuple, str]] = []


def _register():
    for k in (-3, -2, -1, 1, 2, 3, 4, 5):
        OPS.append(("add", (k,), f"xs = [x + {k} for x in xs]" if k > 0 else f"xs = [x - {-k} for x in xs]"))
    for k in (2, 3, -1):
        OPS.append(("mul", (k,), f"xs = [x * {k} for x in xs]" if k != -1 else "xs = [-x for x in xs]"))
    for k in (2, 3, 4, 5):
        OPS.append(("mod", (k,), f"xs = [x % {k} for x in xs]"))
    OPS.append(("keep_even", (), "xs = [x for x in xs if x % 2 == 0]"))
    OPS.append(("keep_odd", (), "xs = [x for x in xs if x % 2 != 0]"))
    for k in (0, 2, 4, 6):
        OPS.append(("keep_gt", (k,), f"xs = [x for x in xs if x > {k}]"))
        OPS.append(("keep_lt", (k,), f"xs = [x for x in xs if x < {k}]"))
    OPS.append(("sort", (), "xs = sorted(xs)"))
    OPS.append(("sort_desc", (), "xs = sorted(xs, reverse=True)"))
    OPS.append(("reverse", (), "xs = xs[::-1]"))
    for k in (1, 2, 3):
        OPS.append(("take", (k,), f"xs = xs[:{k}]"))
        OPS.append(("drop", (k,), f"xs = xs[{k}:]"))
        OPS.append(("rotate", (k,), f"xs = xs[{k} % len(xs):] + xs[:{k} % len(xs)] if xs else xs"))
    OPS.append(("every_other", (), "xs = xs[::2]"))
    OPS.append(("dedup", (), "xs = list(dict.fromkeys(xs))"))
    OPS.append(("prefix_sum", (), "xs = [sum(xs[:i + 1]) for i in range(len(xs))]"))
    OPS.append(("running_max", (), "xs = [max(xs[:i + 1]) for i in range(len(xs))]"))
    OPS.append(("diffs", (), "xs = [b - a for a, b in zip(xs, xs[1:])]"))
    OPS.append(("abs", (), "xs = [abs(x) for x in xs]"))
    OPS.append(("count_each", (), "xs = [xs.count(x) for x in xs]"))


_register()


def program_source(ops: list[int]) -> str:
    body = "\n".join("    " + OPS[i][2] for i in ops)
    return f"def f(xs):\n{body}\n    return xs\n"


def compile_program(ops: list[int]):
    ns: dict = {}
    exec(program_source(ops), ns)  # our own DSL source, never model output
    return ns["f"]


def run(fn, xs):
    try:
        out = fn(list(xs))
        return out if isinstance(out, list) else None
    except Exception:
        return None


def random_input(rng: random.Random, n_min=3, n_max=9) -> list[int]:
    return [rng.randint(-5, 12) for _ in range(rng.randint(n_min, n_max))]


def hidden_inputs(rng: random.Random, n=30) -> list[list[int]]:
    fixed = [[], [0], [7], [3, 3, 3], [-4, 0, 4], [5, 4, 3, 2, 1], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]]
    return fixed + [random_input(rng, 1, 12) for _ in range(n - len(fixed))]


# Alternative programs used for the identifiability check: every depth-1 and
# depth-2 program, compiled once.
_ALTS: list | None = None


def _alternatives():
    global _ALTS
    if _ALTS is None:
        progs = [[i] for i in range(len(OPS))] + [list(p) for p in itertools.product(range(len(OPS)), repeat=2)]
        _ALTS = [(p, compile_program(p)) for p in progs]
    return _ALTS


@dataclass
class Task:
    id: str
    depth: int
    ops: list[int]
    reference: str
    examples: list[dict]
    hidden: list[dict]

    def public(self) -> dict:
        """What the solver may see."""
        return {"id": self.id, "examples": self.examples,
                "signature": "def f(xs: list[int]) -> list[int]"}

    def to_json(self) -> dict:
        return self.__dict__


def make_task(rng: random.Random, depth: int, n_examples=6, extra_random_alts=300) -> Task | None:
    ops = [rng.randrange(len(OPS)) for _ in range(depth)]
    names = [OPS[i][0] for i in ops]
    if len(set(names)) < depth:  # repeated op family is usually degenerate
        return None
    fn = compile_program(ops)
    hid_in = hidden_inputs(rng)
    hid_out = [run(fn, x) for x in hid_in]
    if any(o is None for o in hid_out):
        return None
    # Reject near-trivial functions: identity-like or mostly empty outputs.
    if sum(o == x for o, x in zip(hid_out, hid_in)) > 10 or sum(not o for o in hid_out) > 12:
        return None
    alts = _alternatives() + [
        (p, compile_program(p)) for p in
        ([rng.randrange(len(OPS)) for _ in range(depth)] for _ in range(extra_random_alts))
    ]
    ex_in: list[list[int]] = []
    candidates = alts
    for _ in range(10):
        ex_in.append(random_input(rng))
        ex_out = [run(fn, x) for x in ex_in]
        candidates = [(p, g) for p, g in candidates if [run(g, x) for x in ex_in[-1:]] == ex_out[-1:]]
        if len(ex_in) >= n_examples:
            # Identifiable if every surviving alternative also matches the hidden set.
            if all([run(g, x) for x in hid_in] == hid_out for _, g in candidates):
                break
    else:
        return None
    ex_out = [run(fn, x) for x in ex_in]
    ref = program_source(ops)
    tid = "pbe-" + hashlib.sha1(json.dumps([ops, ex_in]).encode()).hexdigest()[:10]
    return Task(id=tid, depth=depth, ops=ops, reference=ref,
                examples=[{"input": i, "output": o} for i, o in zip(ex_in, ex_out)],
                hidden=[{"input": i, "output": o} for i, o in zip(hid_in, hid_out)])


def generate(n: int, depths: list[int], seed: int, exclude_programs: set | None = None) -> list[Task]:
    """n tasks cycling through ``depths``; programs in ``exclude_programs`` are skipped."""
    rng = random.Random(seed)
    seen = set(exclude_programs or ())
    out: list[Task] = []
    tries = 0
    while len(out) < n:
        tries += 1
        if tries > n * 400:
            raise RuntimeError("could not generate enough identifiable tasks")
        t = make_task(rng, depths[len(out) % len(depths)])
        if t is None or t.reference in seen:
            continue
        seen.add(t.reference)
        out.append(t)
    return out


def build_partitions(spec: dict, seed: int) -> dict[str, list[Task]]:
    """Disjoint partitions: no program appears in two partitions."""
    parts, used = {}, set()
    for i, (name, p) in enumerate(spec.items()):
        tasks = generate(p["n"], p["depths"], seed * 1000 + i, used)
        used |= {t.reference for t in tasks}
        parts[name] = tasks
    return parts


def save(parts: dict[str, list[Task]], path: Path) -> None:
    path.write_text(json.dumps({k: [t.to_json() for t in v] for k, v in parts.items()}))


def load(path: Path) -> dict[str, list[Task]]:
    raw = json.loads(path.read_text())
    return {k: [Task(**t) for t in v] for k, v in raw.items()}
