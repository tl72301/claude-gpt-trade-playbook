from rsi.sandbox import Sandbox, outputs_match


def test_outputs_match_rules():
    assert outputs_match("3\n", "3")
    assert outputs_match("1.50 2\n", "1.5 2")
    assert outputs_match("a  b\n\n", "a b")
    assert not outputs_match("1 2", "1 3")
    assert not outputs_match("1\n2", "1")


def test_run_and_timeout():
    sb = Sandbox("auto", default_timeout_s=2)
    assert sb.run("print(int(input()) * 2)", "21\n").stdout.strip() == "42"
    assert sb.run("while True: pass", timeout_s=1).timed_out


def test_grade_reports_failure_kind():
    sb = Sandbox("auto")
    tests = [{"input": "1 2", "output": "3"}, {"input": "5 5", "output": "10"}]
    assert sb.grade("a,b=map(int,input().split());print(a+b)", tests).passed
    g = sb.grade("print(3)", tests)
    assert not g.passed and g.n_passed == 1 and g.failure["kind"] == "wrong_answer"
    assert sb.grade("raise SystemExit(2)", tests).failure["kind"] == "runtime_error"


def test_bwrap_hides_repo_when_available():
    sb = Sandbox("auto")
    if sb.isolation != "bwrap":
        return
    from rsi.config import ROOT
    out = sb.run(f"import os; print(os.path.exists({str(ROOT)!r}))").stdout.strip()
    assert out == "False"


def test_broker_rejects_non_text_content():
    from rsi.broker import _valid_messages
    assert _valid_messages([{"role": "user", "content": "hi"}])
    assert _valid_messages([{"role": "user", "content": [{"type": "text", "text": "hi"}]}])
    url_image = {"type": "image", "source": {"type": "url", "url": "https://example.com/x.png"}}
    assert not _valid_messages([{"role": "user", "content": [url_image]}])
    assert not _valid_messages([{"role": "user", "content": "hi", "extra": 1}])
    assert not _valid_messages([{"role": "system", "content": "hi"}])
