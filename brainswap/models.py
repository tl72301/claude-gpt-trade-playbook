"""Real model clients. Mock models live in mock.py.

  anthropic       Claude via the Messages API (rsi.llm.AnthropicLLM: refusal and
                  fallback detection, served-model check, per-request pricing)
  openai_compat   any OpenAI-compatible Chat Completions endpoint -- OpenAI itself,
                  or Gemini via https://generativelanguage.googleapis.com/v1beta/openai/

STATUS: neither client has been exercised against a live API in this repo.
"""

from __future__ import annotations

import os

from rsi.llm import AnthropicLLM, LLMResult, price_entry, request_cost


class OpenAICompatLLM:
    def __init__(self, model: str, prices: dict, base_url: str | None, api_key_env: str,
                 max_tokens: int = 16000, extra_params: dict | None = None):
        from openai import OpenAI  # lazy: mock runs need no SDK

        key = os.environ.get(api_key_env)
        if not key:
            raise RuntimeError(f"{api_key_env} is not set")
        self.client = OpenAI(api_key=key, base_url=base_url, max_retries=8, timeout=600)
        self.model, self.max_tokens = model, max_tokens
        self.extra = dict(extra_params or {})
        self.price = price_entry(model, prices)

    def complete(self, messages, system=None, max_tokens=None, context=None) -> LLMResult:
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        r = self.client.chat.completions.create(model=self.model, messages=msgs,
                                                max_completion_tokens=max_tokens or self.max_tokens,
                                                **self.extra)
        choice = r.choices[0]
        usage = r.usage
        n_in = int(getattr(usage, "prompt_tokens", 0) or 0)
        n_out = int(getattr(usage, "completion_tokens", 0) or 0)   # includes reasoning tokens
        refused = bool(getattr(choice.message, "refusal", None)) or choice.finish_reason == "content_filter"
        return LLMResult(text=choice.message.content or "", requested_model=self.model,
                         served_model=getattr(r, "model", None) or self.model,
                         stop_reason="refusal" if refused else choice.finish_reason,
                         input_tokens=n_in, output_tokens=n_out,
                         cost_usd=request_cost(self.price, n_in, n_out))


def make_model(spec: dict, prices: dict, *, mock_scenario: str | None, tasks: dict):
    if mock_scenario:
        from .mock import MockModel
        return MockModel(f"mock-{spec['mock_style']}", spec["mock_style"], mock_scenario, tasks, prices,
                         priced_as=spec["model"])
    if spec["provider"] == "anthropic":
        return AnthropicLLM(spec["model"], prices, effort=spec.get("effort"),
                            max_tokens=spec.get("max_tokens", 16000), extra_params=spec.get("extra_params"))
    if spec["provider"] == "openai_compat":
        return OpenAICompatLLM(spec["model"], prices, spec.get("base_url"), spec["api_key_env"],
                               spec.get("max_tokens", 16000), spec.get("extra_params"))
    raise ValueError(f"unknown provider {spec['provider']!r}")
