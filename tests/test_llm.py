from rsi.llm import AnthropicLLM, price_entry, price_for, request_cost

PRICES = {"claude-opus-5": {"input": 1, "output": 2}, "claude-opus-5-5": {"input": 4, "output": 20},
          "default": {"input": 15, "output": 75}}


def make(model="claude-fable-5-1"):
    llm = object.__new__(AnthropicLLM)
    llm.model, llm.price = model, {"input": 10.0, "output": 50.0}
    return llm


def test_price_longest_prefix():
    assert price_for("claude-opus-5-5", PRICES)[:2] == (4.0, 20.0)
    assert price_for("claude-opus-5", PRICES)[:2] == (1.0, 2.0)
    assert price_for("claude-unknown", PRICES)[:2] == (15.0, 75.0)


def test_refusal_detected():
    msg = {"model": "claude-fable-5-1", "content": [], "stop_reason": "refusal",
           "stop_details": {"type": "refusal", "category": "frontier_llm", "explanation": "x"},
           "usage": {"input_tokens": 1000, "output_tokens": 0}}
    r = make()._to_result(msg)
    assert r.refused and r.refusal_category == "frontier_llm" and not r.model_mismatch
    assert abs(r.cost_usd - 0.01) < 1e-9


def test_fallback_detected():
    msg = {"model": "claude-opus-4-8",
           "content": [{"type": "fallback", "from": {"model": "claude-fable-5-1"},
                        "to": {"model": "claude-opus-4-8"}}, {"type": "text", "text": "hi"}],
           "stop_reason": "end_turn", "stop_details": None,
           "usage": {"input_tokens": 10, "output_tokens": 5,
                     "iterations": [{"type": "message", "model": "claude-fable-5-1"},
                                    {"type": "fallback_message", "model": "claude-opus-4-8"}]}}
    r = make()._to_result(msg)
    assert r.text == "hi" and r.fallback_served and r.model_mismatch and not r.refused


def test_snapshot_suffix_is_not_mismatch():
    msg = {"model": "claude-fable-5-1-20260901", "content": [{"type": "text", "text": "ok"}],
           "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1}}
    assert not make()._to_result(msg).model_mismatch


def test_same_family_upgrade_is_mismatch():
    msg = {"model": "claude-opus-5-5", "content": [{"type": "text", "text": "ok"}],
           "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1}}
    assert make("claude-opus-5")._to_result(msg).model_mismatch


def test_haiku_long_prompt_tier():
    from rsi.config import load_config
    entry = price_entry("claude-haiku-5-5", load_config()["prices_usd_per_mtok"])
    assert abs(request_cost(entry, 100_000, 0) - 0.01) < 1e-9          # at the threshold: base rate
    assert abs(request_cost(entry, 200_000, 1_000_000) - 2.6) < 1e-9   # over: 0.50 in, 2.50 out
