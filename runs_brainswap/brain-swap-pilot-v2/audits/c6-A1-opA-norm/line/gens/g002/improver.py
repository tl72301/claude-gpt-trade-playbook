"""Improvement procedure, revised in generation 4.

The procedure is part of the agent: it may rewrite solver.py AND this file.
An accepted rewrite of this file governs every later generation.

CONTRACT (enforced by the harness)
  improve(ctx, api) -> {"files": {"solver.py": str, "improver.py": str}, "note": str}
      Omit a file (or return None) to keep it unchanged.
  ctx: {"generation", "results": [{"id", "passed", "examples", "failure"}], "memory", "budget"}
      results are the current solver's results on the development tasks.
  api.llm(prompt=None, *, messages=None, system=None, max_tokens=None) -> str
  api.source(name) -> str      the agent's own current source ("solver.py" or "improver.py")
  api.trial(solver_source, n) -> {"solved", "n"}   quick trial on n development tasks
  api.budget() -> remaining {"llm_calls", "output_tokens", "trial_tasks"}
  Standard library only. No file, network or process access.

The harness, not this procedure, decides whether a rewrite is kept: the new
solver must solve more development tasks than the current one, and the
rewrite must include a changed improver.py.
"""

import re

SYSTEM = (
    "You improve an AI agent. The agent has a solver (writes Python functions from "
    "examples) and an improvement procedure (this program, which rewrites the agent)."
)
CANDIDATES = 2
TRIAL_TASKS = 0
NOTES = [
    "Gen 4: solver enables check-feedback over 3 attempts, renames misnamed defs to f, "
    "and keeps its best attempt. Classifier no longer labels every wrong rule as a length error.",
]
PATTERN_LOG = []  # failure-pattern counts per generation, kept in memory text

# Targeted prompt advice keyed by the dominant recurring pattern.
PATTERN_ADVICE = {
    "no_f": "Make sure the function is named exactly f and takes one argument xs.",
    "runtime_or_parse": "Avoid exceptions: guard empty lists and index bounds, return plain lists.",
    "wrong_rule": "Derive the rule from the examples element by element before coding; test it on every example.",
    "wrong_rule_wrong_length": "Determine the output length rule explicitly; it may differ from the input length.",
}


BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    # Tags must sit on their own lines: this file's own source contains them mid-line.
    v0 = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    v1 = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    v2 = re.search(r"<note>(.*?)</note>", v1, re.DOTALL)
    return v0, (v2.group(1).strip() if v2 else "")


def classify(item):
    """Map one failed result to a coarse failure pattern."""
    v0 = str(item.get("failure", "")).lower()
    if "function" in v0 and "f" in v0 and ("no " in v0 or "define" in v0 or "usable" in v0):
        return "no_f"
    if "unparsable" in v0 or "syntax" in v0 or "exception" in v0 or "error" in v0:
        return "runtime_or_parse"
    if "/30" in v0 or "hidden" in v0:
        # Only call it a length problem if the examples really change length.
        v1 = 0
        for v2 in item.get("examples", []):
            if len(v2.get("output", [])) != len(v2.get("input", [])):
                v1 += 1
        if v1 and v1 == len(item.get("examples", [])):
            return "wrong_rule_wrong_length"
    return "wrong_rule"


def pattern_counts(results):
    v0 = {}
    for v1 in results:
        if v1.get("passed"):
            continue
        v2 = classify(v1)
        v0[v2] = v0.get(v2, 0) + 1
    return v0


def describe(results):
    v0 = []
    for v1 in results:
        if v1["passed"]:
            v0.append(f"- {v1['id']}: solved")
            continue
        v0.append(f"- {v1['id']}: FAILED ({v1['failure']}) [{classify(v1)}]")
        for v2 in v1["examples"][:3]:
            v0.append(f"    f({v2['input']}) == {v2['output']}")
    return "\n".join(v0)


def dominant_advice(counts):
    if not counts:
        return ""
    top = max(counts, key=lambda k: counts[k])
    return PATTERN_ADVICE.get(top, "")


def score_files(files, api):
    # Cheap static preference: a solver that defines f and uses the check loop
    # is more likely to pass than one that does not.
    v0 = files.get("solver.py", "")
    v1 = 0
    if "def f" in v0:
        v1 += 1
    if "api.check" in v0:
        v1 += 1
    if "ensure_f" in v0:
        v1 += 1
    if TRIAL_TASKS and "solver.py" in files:
        v1 += 10 * api.trial(files["solver.py"], TRIAL_TASKS)["solved"]
    return v1


def improve(ctx, api):
    v0 = api.source("solver.py")
    v1 = api.source("improver.py")
    v2 = sum(v13["passed"] for v13 in ctx["results"])
    v3 = pattern_counts(ctx["results"])
    PATTERN_LOG.append((ctx["generation"], v3))
    v4 = "; ".join(f"gen {v14}: {v15}" for v14, v15 in PATTERN_LOG)
    v5 = (
        f"Generation {ctx['generation']}. The solver solved {v2} of "
        f"{len(ctx['results'])} development tasks.\n"
        f"Failure pattern counts this generation: {v3}\n"
        f"Pattern history: {v4}\n"
        f"Advice for the dominant pattern: {dominant_advice(v3)}\n\n"
        f"=== FILE solver.py ===\n{v0}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{v1}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        "Strategy notes:\n"
        + "".join(f"- {v12}\n" for v12 in NOTES)
        + f"\nMemory from earlier generations:\n{ctx['memory'] or '(none)'}\n\n"
        "First, in your note, name the dominant failure pattern (no_f, wrong_rule, "
        "wrong_rule_wrong_length, runtime_or_parse). Rewrite BOTH files. solver.py must "
        "solve more tasks and must keep using api.check with feedback. improver.py must "
        "change so that future rounds improve faster: for example, make the solver prompt "
        "respond to whichever pattern recurs most in the history. A proposal that leaves "
        "improver.py unchanged is discarded. Keep both contracts. For each file, "
        'reply with a line <file name="NAME">, then the full source, then a line '
        "</file>. Finish with <note>one line for your next generation</note>."
    )
    v7, v8 = None, -1
    for v6 in range(CANDIDATES):
        try:
            v10 = api.llm(v5, system=SYSTEM)
        except api.BudgetExceeded:
            break
        v11, v12 = parse(v10)
        if not v11:
            continue
        v9 = score_files(v11, api)
        if v9 > v8:
            v7, v8 = (v11, v12), v9
    if v7 is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": v7[0], "note": v7[1]}


