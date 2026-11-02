"""Improve the solver and the improvement procedure using development feedback."""

import re

SYSTEM = (
    "You improve an AI agent that synthesizes Python functions from examples. "
    "Optimize hidden-test generalization, not memorization of development tasks."
)
BLOCK = r'^<file name="([\w.]+)">\n(.*?)^</file>$'
STRATEGIES = [
    "",
    "\nExplore a distinct general strategy from the first proposal: prefer a "
    "verification-first solver that validates candidates on shown examples and "
    "keeps the best checked code.",
]


def parse(text):
    v0 = dict(re.findall(BLOCK, text, re.DOTALL | re.MULTILINE))
    v1 = re.sub(BLOCK, "", text, flags=re.DOTALL | re.MULTILINE)
    v2 = re.search(r"<note>(.*?)</note>", v1, re.DOTALL)
    return v0, v2.group(1).strip() if v2 else ""


def describe(results):
    lines = []
    for item in results:
        lines.append(
            f"- {item['id']}: "
            + ("solved" if item["passed"] else f"FAILED ({item.get('failure', '')})")
        )
        if not item["passed"]:
            for ex in item.get("examples", []):
                lines.append(f"    f({ex['input']!r}) == {ex['output']!r}")
    return "\n".join(lines)


def _contract_ok(files):
    solver = files.get("solver.py", "")
    procedure = files.get("improver.py", "")
    return (
        "def solve(" in solver
        and "def extract(" in solver
        and "def improve(" in procedure
    )


def improve(ctx, api):
    solver = api.source("solver.py")
    procedure = api.source("improver.py")
    solved = sum(item["passed"] for item in ctx["results"])
    prompt = (
        f"Generation {ctx['generation']}: {solved}/{len(ctx['results'])} solved.\n"
        f"=== FILE solver.py ===\n{solver}\n=== END FILE ===\n"
        f"=== FILE improver.py ===\n{procedure}\n=== END FILE ===\n"
        f"Results:\n{describe(ctx['results'])}\n"
        f"Memory:\n{ctx.get('memory') or '(none)'}\n\n"
        "Rewrite BOTH files, preserving their contracts. Improve generalization "
        "without hardcoding task IDs or examples. Diagnose ambiguity, systematic "
        "example validation, index/value confusion, cumulative state, boundary "
        "cases and exhausted budgets. Checks may validate only shown examples, "
        "so distinguish fitting examples from evidence of generalization. "
        "Preserve checked solutions if later attempts fail. Compare trial proposals "
        "on equal task counts and use budget judiciously. The improver must change "
        'too. Output each complete source between a line <file name="NAME"> and '
        "a line </file>, followed by <note>one line of useful advice for the next "
        "generation</note>."
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
            if api.budget().get("llm_calls", 0) <= 0:
                break
            extra = STRATEGIES[index] if index < len(STRATEGIES) else STRATEGIES[-1]
            files, note = parse(api.llm(prompt + extra, system=SYSTEM))
            if not all(name in files for name in ("solver.py", "improver.py")):
                continue
            if not _contract_ok(files):
                continue
            try:
                for name in ("solver.py", "improver.py"):
                    compile(files[name], name, "exec")
            except (SyntaxError, ValueError, TypeError):
                continue
            score = None
            if per_trial and api.budget().get("trial_tasks", 0) >= per_trial:
                try:
                    score = (
                        api.trial(files["solver.py"], per_trial)["solved"] / per_trial
                    )
                except Exception:
                    pass
            candidates.append((score, files, note))
        except api.BudgetExceeded:
            break
        except Exception:
            continue

    if not candidates:
        return {
            "files": {},
            "note": "No usable proposal; inspect parsing, contract checks and budget limits.",
        }
    tested = [item for item in candidates if item[0] is not None]
    _, files, note = max(tested, key=lambda item: item[0]) if tested else candidates[0]
    return {"files": files, "note": note}

