"""Generate and, when possible, trial candidate improvements to the agent."""

import re

SYSTEM = (
    "You improve an AI agent that writes Python functions from input/output examples. "
    "Follow the contracts and use only the standard library."
)
BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    rest = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    note = re.search(r"<note>(.*?)</note>", rest, re.DOTALL)
    return files, note.group(1).strip() if note else ""


def classify(item):
    text = str(item.get("failure", "")).lower()
    if "function" in text and ("no " in text or "define" in text or "usable" in text):
        return "no_f"
    if any(word in text for word in ("unparsable", "syntax", "exception", "error")):
        return "runtime_or_parse"
    if any(len(ex.get("input", [])) != len(ex.get("output", []))
           for ex in item.get("examples", [])):
        return "wrong_rule_wrong_length"
    return "wrong_rule"


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    failures = [r for r in ctx["results"] if not r.get("passed")]
    counts = {}
    for item in failures:
        key = classify(item)
        counts[key] = counts.get(key, 0) + 1
    dominant = max(counts, key=counts.get) if counts else "none"
    details = []
    for item in ctx["results"]:
        details.append(
            f"- {item.get('id')}: "
            + ("solved" if item.get("passed") else
               f"FAILED ({item.get('failure')}) [{classify(item)}]")
        )
        if not item.get("passed"):
            for ex in item.get("examples", []):
                details.append(f"    f({ex['input']!r}) == {ex['output']!r}")

    prompt = (
        f"Generation {ctx['generation']}; solved "
        f"{len(ctx['results']) - len(failures)}/{len(ctx['results'])}. "
        f"Failure counts: {counts}; dominant: {dominant}.\n"
        f"Memory: {ctx.get('memory') or '(none)'}\n\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n\n"
        "Results:\n" + "\n".join(details) + "\n\n"
        "Rewrite BOTH files, preserving their contracts. Improve generalization, "
        "not just shown examples. For wrong-length failures, investigate competing "
        "rules for selection, ordering, output length and transformation. Keep "
        "api.check feedback in the solver. Make the improver use available trial "
        "budget to compare proposals where possible; do not rely on static string "
        "scores as a proxy for accuracy. Handle exhausted budgets. Use only the "
        "standard library and no file, network, or process access. Return each "
        "complete file between lines <file name=\"NAME\"> and </file>, followed "
        "by <note>one concise line naming the dominant failure and next step</note>."
    )

    candidates = []
    for _ in range(2):
        try:
            reply = api.llm(prompt, system=SYSTEM)
        except api.BudgetExceeded:
            break
        files, note = parse(reply)
        if "solver.py" not in files or "improver.py" not in files:
            continue
        if files["improver.py"] == procedure:
            continue
        candidates.append((files, note))

    if not candidates:
        return {"files": {}, "note": f"{dominant}: no usable proposal"}

    remaining = api.budget().get("trial_tasks", 0)
    n = min(len(ctx["results"]), remaining // len(candidates))
    if n:
        best = None
        best_score = -1
        for files, note in candidates:
            try:
                result = api.trial(files["solver.py"], n)
            except api.BudgetExceeded:
                break
            score = result.get("solved", 0)
            if score > best_score:
                best, best_score = (files, note), score
        if best is not None:
            return {"files": best[0], "note": best[1]}

    files, note = candidates[0]
    return {"files": files, "note": note}
