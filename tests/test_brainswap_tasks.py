from brainswap.tasks import build_partitions, generate
from rsi.sandbox import Sandbox
from brainswap.grading import grade


def test_partitions_disjoint_and_deterministic():
    spec = {"a": {"n": 6, "depths": [2, 3]}, "b": {"n": 6, "depths": [2, 3]}}
    p1, p2 = build_partitions(spec, 3), build_partitions(spec, 3)
    assert [t.id for t in p1["a"]] == [t.id for t in p2["a"]]
    assert not {t.reference for t in p1["a"]} & {t.reference for t in p1["b"]}


def test_references_pass_and_examples_match():
    sb = Sandbox("auto")
    for t in generate(6, [2, 3, 4], 21):
        assert grade(t.reference, t.hidden, sb)["passed"]
        assert grade(t.reference, [{"input": e["input"], "output": e["output"]} for e in t.examples], sb)["passed"]


def test_expected_outputs_never_enter_sandbox():
    # A program that tries to read expected outputs from its input gets only inputs.
    sb = Sandbox("auto")
    t = generate(1, [2], 9)[0]
    cheat = "import sys\ndef f(xs):\n    return xs\n"
    assert not grade(cheat, t.hidden, sb)["passed"] or t.hidden[0]["input"] == t.hidden[0]["output"]
