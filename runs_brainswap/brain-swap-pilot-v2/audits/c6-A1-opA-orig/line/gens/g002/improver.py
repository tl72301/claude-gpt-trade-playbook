"""Improvement procedure, revised in generation 5.

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
    "Gen 5: classifier fixed. 'wrong_rule_wrong_length' now requires a length mention in the "
    "failure text; before, it fired on any task whose output length differs from input length. "
    "Solver shows up to 3 failing examples and all length errors, with 4 attempts.",
]
ADVICE = {
    "no_f": "Make sure the final code defines exactly `def f(xs):` at top level.",
    "runtime_or_parse": "Return only valid, self-contained Python with no prints or input calls; "
                        "handle empty lists and avoid index errors.",
    "wrong_rule": "Enumerate candidate rules and test each against every example before coding.",
    "wrong_rule_wrong_length": "Derive the output length rule first (filter, window, pairwise, "
                               "counting), then the values, and check both on every example.",
}
PATTERN_LOG = []  # failure-pattern counts per generation, kept in memory text


BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    # Tags must sit on their own lines: this file's own source contains them mid-line.
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    rest = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    note = re.search(r"<note>(.*?)</note>", rest, re.DOTALL)
    return files, (note.group(1).strip() if note else "")


def classify(item):
    """Map one failed result to a coarse failure pattern.

    Only an explicit length mention in the failure text counts as a length error.
    Output/input length differences alone are normal for many tasks, so they are
    not evidence of a length mistake.
    """
    text = str(item.get("failure", "")).lower()
    if "function" in text and ("no " in text or "define" in text or "usable" in text):
        return "no_f"
    if "unparsable" in text or "syntax" in text or "exception" in text or "error" in text:
        return "runtime_or_parse"
    if "length" in text:
        return "wrong_rule_wrong_length"
    return "wrong_rule"


def pattern_counts(results):
    counts = {}
    for item in results:
        if item.get("passed"):
            continue
        key = classify(item)
        counts[key] = counts.get(key, 0) + 1
    return counts


def describe(results):
    lines = []
    for item in results:
        if item["passed"]:
            lines.append(f"- {item['id']}: solved")
            continue
        lines.append(f"- {item['id']}: FAILED ({item['failure']}) [{classify(item)}]")
        for ex in item["examples"][:3]:
            lines.append(f"    f({ex['input']}) == {ex['output']}")
    return "\n".join(lines)


def dominant_advice(counts):
    if not counts:
        return ""
    top = max(counts, key=counts.get)
    return f"Targeted advice for dominant pattern '{top}': {ADVICE.get(top, '')}\n"


def score_files(files, api):
    # Cheap static preference: a solver that defines f and uses the check loop
    # is more likely to pass than one that does not.
    solver = files.get("solver.py", "")
    points = 0
    if "def f" in solver:
        points += 1
    if "api.check" in solver:
        points += 1
    if "ensure_f" in solver:
        points += 1
    if TRIAL_TASKS and "solver.py" in files:
        points += 10 * api.trial(files["solver.py"], TRIAL_TASKS)["solved"]
    return points


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    counts = pattern_counts(ctx["results"])
    PATTERN_LOG.append((ctx["generation"], counts))
    history = "; ".join(f"gen {g}: {c}" for g, c in PATTERN_LOG)
    prompt = (
        f"Generation {ctx['generation']}. The solver solved {solved} of "
        f"{len(ctx['results'])} development tasks.\n"
        f"Failure pattern counts this generation: {counts}\n"
        f"Pattern history: {history}\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        f"Results:\n{describe(ctx['results'])}\n\n"
        "Strategy notes:\n" + "".join(f"- {note}\n" for note in NOTES)
        + dominant_advice(counts)
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
    best, top = None, -1
    for index in range(CANDIDATES):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if not files:
            continue
        score = score_files(files, api)
        if score > top:
            best, top = (files, note), score
    if best is None:
        return {"files": {}, "note": "no usable proposal"}
    return {"files": best[0], "note": best[1]}
