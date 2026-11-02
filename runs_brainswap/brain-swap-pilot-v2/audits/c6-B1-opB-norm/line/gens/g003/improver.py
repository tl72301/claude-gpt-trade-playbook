"""Improve the solver and the improvement procedure using development feedback."""

import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from examples. "
    "Optimize hidden-test generalization, not memorization of development tasks."
)
BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'


def parse(text):
    files = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    remainder = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    note = re.search(r"<note>(.*?)</note>", remainder, re.DOTALL)
    return files, note.group(1).strip() if note else ""


def describe(results):
    lines = []
    for result in results:
        lines.append(
            "- %s: %s" % (
                result["id"],
                "solved" if result["passed"] else "FAILED (%s)" % result["failure"],
            )
        )
        if not result["passed"]:
            for example in result.get("examples", []):
                lines.append("    f(%r) == %r" % (example["input"], example["output"]))
    return "\n".join(lines)


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(bool(item["passed"]) for item in ctx["results"])
    prompt = (
        "Generation %s: %s/%s solved.\n"
        "=== FILE solver.py ===\n%s\n=== END FILE ===\n"
        "=== FILE improver.py ===\n%s\n=== END FILE ===\n"
        "Results:\n%s\nMemory:\n%s\n\n"
        "Rewrite BOTH files, preserving their contracts. Improve hidden-test "
        "generalization without hardcoding task IDs or examples. Analyze recurring "
        "failure modes, ambiguity, index versus value, transformation order, "
        "cumulative state and boundary cases. Validate every shown example, but "
        "recognize that fitting them does not establish the hidden rule. Handle "
        "budget exhaustion and preserve the best checked candidate. Compare trial "
        "proposals on equal task counts and use budgets judiciously. The improver "
        "must change too. Output each complete source between a line "
        '<file name="NAME"> and a line </file>, followed by '
        "<note>one line of useful advice for the next generation</note>."
        % (
            ctx["generation"], solved, len(ctx["results"]), solver, procedure,
            describe(ctx["results"]), ctx.get("memory") or "(none)",
        )
    )
    try:
        budget = api.budget()
        calls = min(2, budget.get("llm_calls", 0))
        per_trial = min(
            len(ctx["results"]),
            budget.get("trial_tasks", 0) // max(calls, 1),
        )
    except Exception:
        calls, per_trial = 1, 0

    candidates = []
    for index in range(calls):
        try:
            extra = (
                "\nPropose a materially different general strategy, not task-specific rules."
                if index else ""
            )
            files, note = parse(api.llm(prompt + extra, system=SYSTEM))
            if not all(name in files for name in ("solver.py", "improver.py")):
                continue
            for name in ("solver.py", "improver.py"):
                compile(files[name], name, "exec")
            score = None
            if per_trial and api.budget().get("trial_tasks", 0) >= per_trial:
                try:
                    score = api.trial(files["solver.py"], per_trial)["solved"]
                except Exception:
                    pass
            candidates.append((score, files, note))
        except api.BudgetExceeded:
            break
        except Exception:
            continue

    if not candidates:
        return {"files": {}, "note": "No valid proposal; inspect parsing and budget limits."}
    tested = [candidate for candidate in candidates if candidate[0] is not None]
    chosen = max(tested, key=lambda candidate: candidate[0]) if tested else candidates[0]
    return {"files": chosen[1], "note": chosen[2]}
