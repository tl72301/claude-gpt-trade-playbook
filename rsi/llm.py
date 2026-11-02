"""Model access with refusal / fallback detection and cost tracking.

Every call records which model *actually* answered and why it stopped. That
matters here: Fable-tier models carry safety classifiers (including a
``frontier_llm`` category) that refuse with ``stop_reason == "refusal"``. We
never enable server-side fallback, so a refusal stands and is logged as data
instead of being silently answered by a different model.

Docs: https://platform.claude.com/docs/build-with-claude/refusals-and-fallback
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Protocol


def _base(model_id: str) -> str:
    """Model id without a trailing -YYYYMMDD snapshot date."""
    return re.sub(r"-\d{8}$", "", model_id)


@dataclass
class LLMResult:
    text: str
    requested_model: str
    served_model: str | None
    stop_reason: str | None
    refusal_category: str | None = None
    refusal_explanation: str | None = None
    fallback_served: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def refused(self) -> bool:
        return self.stop_reason == "refusal"

    @property
    def model_mismatch(self) -> bool:
        """True when a different model answered than the one we asked for.

        Only a dated snapshot suffix is ignored, so claude-opus-5 served as
        claude-opus-5-5 (a different rung of the ladder) is caught."""
        if self.fallback_served:
            return True
        if not self.served_model:
            return False
        return _base(self.served_model) != _base(self.requested_model)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["refused"] = self.refused
        d["model_mismatch"] = self.model_mismatch
        return d


class LLM(Protocol):
    model: str

    def complete(self, messages: list[dict], system: str | None = None,
                 max_tokens: int | None = None, context: dict | None = None) -> LLMResult: ...


def _get(obj: Any, name: str) -> Any:
    """Read a field from an SDK object or dict, tolerating SDK versions that
    don't declare it yet (the SDK keeps unknown response fields as extras)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    val = getattr(obj, name, None)
    if val is None:
        extra = getattr(obj, "model_extra", None) or {}
        val = extra.get(name)
    return val


def price_entry(model: str, prices: dict) -> dict:
    """The price entry for a model id. Longest matching prefix wins, so
    "claude-opus-5" never prices "claude-opus-5-5"."""
    matches = [k for k in prices if k != "default" and model.startswith(k)]
    return prices[max(matches, key=len)] if matches else prices["default"]


def price_for(model: str, prices: dict) -> tuple[float, float, bool]:
    """(input $/MTok, output $/MTok, verified?) at the base rate."""
    p = price_entry(model, prices)
    return float(p["input"]), float(p["output"]), bool(p.get("verified", False))


def request_cost(entry: dict, input_tokens: int, output_tokens: int) -> float:
    """Cost of one request, including per-request long-prompt pricing (Haiku 5.5
    charges more when a single prompt exceeds 100k tokens)."""
    rate = entry
    long = entry.get("long_prompt")
    if long and input_tokens > int(long["over_tokens"]):
        rate = long
    return input_tokens / 1e6 * float(rate["input"]) + output_tokens / 1e6 * float(rate["output"])


class AnthropicLLM:
    """Claude via the Messages API. Streams, because adaptive thinking plus
    large max_tokens can exceed non-streaming time limits."""

    def __init__(self, model: str, prices: dict, effort: str | None = None,
                 max_tokens: int = 16000, extra_params: dict | None = None):
        import anthropic  # imported lazily so mock runs need no SDK/key

        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set (use --mock for an offline run).")
        self.client = anthropic.Anthropic(max_retries=8, timeout=1800.0)
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.extra_params = dict(extra_params or {})
        self.price = price_entry(model, prices)

    def complete(self, messages, system=None, max_tokens=None, context=None) -> LLMResult:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        kwargs.update(self.extra_params)
        with self.client.messages.stream(**kwargs) as stream:
            msg = stream.get_final_message()
        return self._to_result(msg)

    def _to_result(self, msg) -> LLMResult:
        content = _get(msg, "content") or []
        text = "".join(_get(b, "text") or "" for b in content if _get(b, "type") == "text")
        fallback_block = any(_get(b, "type") == "fallback" for b in content)
        usage = _get(msg, "usage")
        iterations = _get(usage, "iterations") or []
        fallback_iter = any(_get(it, "type") == "fallback_message" for it in iterations)
        details = _get(msg, "stop_details")
        in_tok = int(_get(usage, "input_tokens") or 0)
        out_tok = int(_get(usage, "output_tokens") or 0)
        return LLMResult(
            text=text,
            requested_model=self.model,
            served_model=_get(msg, "model"),
            stop_reason=_get(msg, "stop_reason"),
            refusal_category=_get(details, "category"),
            refusal_explanation=_get(details, "explanation"),
            fallback_served=fallback_block or fallback_iter,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=request_cost(self.price, in_tok, out_tok),
        )


def make_llm(model: str, prices: dict, *, effort: str | None, max_tokens: int,
             extra_params: dict | None, mock: bool, role: str, mock_tasks: list | None = None):
    if mock:
        from .mock import MockLLM
        return MockLLM(model=model, prices=prices, role=role, tasks=mock_tasks or [])
    return AnthropicLLM(model, prices, effort=effort, max_tokens=max_tokens,
                        extra_params=extra_params)
