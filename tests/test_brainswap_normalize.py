"""The presentation interventions: safe subset, verification, and behavior preservation."""

import pytest

from brainswap.experiment import seed_files
from brainswap.normalize import CONDITIONS, present, rename, token_count, unsupported_reason
from brainswap.tasks import generate


@pytest.mark.parametrize("cond", CONDITIONS)
@pytest.mark.parametrize("name", ["solver.py", "improver.py"])
def test_seed_presentations_verified(name, cond):
    out, rep = present(seed_files()[name], cond)
    assert rep.verified and rep.coverage == 1.0
    compile(out, name, "exec")


def test_neutral_is_length_matched_norm_is_not():
    src = seed_files()["improver.py"]
    _, neutral = present(src, "neutral")
    _, norm = present(src, "norm")
    assert abs(neutral.tokens_after - neutral.tokens_before) / neutral.tokens_before < 0.02
    assert norm.tokens_after < norm.tokens_before


@pytest.mark.parametrize("body", [
    "    def g():\n        return y\n    y = 1\n    return g()\n",
    "    global z\n    z = 1\n    return z\n",
    "    y = 1\n    return f'{y=}'\n",
    "    y = 1\n    return locals()\n",
    "    import re\n    y = 1\n    return y\n",
    "    y = [1]\n    return [(w := v) for v in y]\n",
])
def test_unsupported_functions_left_alone(body):
    src = "def f(x):\n" + body
    out, rep = present(src, "norm")
    assert "f" in rep.unsupported and rep.renamed == 0 and rep.coverage < 1.0


def test_strings_and_params_untouched():
    import ast
    src = "def f(prompt, api):\n    reply = api.llm(prompt + ' reply')\n    return f'{reply}!'\n"
    out, rep = present(src, "norm")
    consts = lambda s: sorted(n.value for n in ast.walk(ast.parse(s)) if isinstance(n, ast.Constant))
    assert consts(out) == consts(src)               # string VALUES unchanged (black may change quotes)
    assert "def f(prompt, api)" in out and "reply =" not in out


def test_collision_with_existing_identifier_avoided():
    src = "v0 = 5\ndef f(x):\n    y = x + v0\n    return y\n"
    out, rep = present(src, "norm")
    assert rep.verified and "v0 = 5" in out and "v1" in out    # local y -> v1, global v0 untouched
    ns = {}
    exec(out, ns)
    assert ns["f"](1) == 6


def test_bad_plan_rejected():
    src = "def f(x):\n    a = 1\n    b = 2\n    return a + b + x\n"
    out, rep = rename(src, {"f": {"a": "b"}})          # collides with existing local
    assert out == src and rep.renamed == 0


class Recorder:
    """A deterministic stand-in for the harness API that records every call."""

    class BudgetExceeded(Exception):
        pass

    def __init__(self):
        self.calls = []

    def llm(self, prompt=None, *, messages=None, system=None, max_tokens=None):
        self.calls.append(("llm", prompt, messages, system))
        n = len(self.calls)
        return f"```python\ndef f(xs):\n    return xs[:{n}]\n```"

    def check(self, code):
        self.calls.append(("check", code))
        return [{"passed": False, "input": [1, 2], "expected": [2], "actual": [1]}]

    def source(self, name):
        self.calls.append(("source", name))
        return f"# source of {name}\n"

    def trial(self, src, n):
        self.calls.append(("trial", src, n))
        return {"solved": len(src) % 3, "n": n}

    def budget(self):
        return {}


def _run(src, entry, payload):
    ns = {"__name__": "agent"}
    exec(src, ns)
    api = Recorder()
    return ns[entry](payload, api), api.calls


@pytest.mark.parametrize("cond", CONDITIONS)
def test_presented_code_behaves_identically(cond):
    """Differential check: identical prompts, tool calls and return values."""
    seed = seed_files()
    task = generate(1, [3], 5)[0].public()
    solver = seed["solver.py"].replace("ATTEMPTS = 1", "ATTEMPTS = 3").replace("USE_CHECK = False", "USE_CHECK = True")
    improver = seed["improver.py"].replace("CANDIDATES = 1", "CANDIDATES = 2").replace("TRIAL_TASKS = 0", "TRIAL_TASKS = 3")
    ctx = {"generation": 2, "results": [{"id": "t", "passed": False, "examples": task["examples"],
                                         "failure": "3/30"}], "memory": "m", "budget": {}}
    for src, entry, payload in ((solver, "solve", task), (improver, "improve", ctx)):
        out, rep = present(src, cond)
        assert rep.verified
        assert _run(src, entry, payload) == _run(out, entry, payload)


def test_token_count_monotone():
    assert token_count("a") < token_count("a = b + c")
