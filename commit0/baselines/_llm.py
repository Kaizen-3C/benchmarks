"""Provider-agnostic LLM client + pricing.

⚠️ DUAL-REPO FILE — sync manually on changes.
This file is duplicated between:
  - Kaizen-3C/benchmarks/commit0/baselines/_llm.py   (public, MIT)
  - kaizen-delta/benchmarks/commit0/baselines/_llm.py (private dev mirror)
Per `benchmarks/MIGRATION_PLAN.md` §"The dependency question" Option A:
~110 lines, low churn (twice in the entire 2026-04 campaign), so we accept
the duplication cost over a shared package. If this file grows past ~500
lines or sees frequent churn, escalate to a published `kaizen-llm` PyPI pkg.

Extracted from kaizen_delta.py so any new baseline script can do:

    from _llm import LLMClient, cost
    client = LLMClient(args.provider, args.model)
    response, usage = client.call(instructions, cached_block)

Both providers expose the same call signature. Caching is handled
automatically:
  - Anthropic: explicit `cache_control: ephemeral` on the cached_block.
  - OpenAI: cached_block prepended to instructions; OpenAI's auto-cache
    matches identical prefixes across calls within ~5 min.

Pricing constants reflect 2026-04 list pricing. Update if model pricing
changes.
"""

from __future__ import annotations

import os


# Sonnet 4.6 list pricing ($/MTok)
SONNET_INPUT  = 3.00
SONNET_OUTPUT = 15.00
SONNET_CACHE_READ  = 0.30
SONNET_CACHE_WRITE = 3.75

# GPT-5.4 list pricing ($/MTok, approx)
GPT54_INPUT  = 1.25
GPT54_OUTPUT = 10.00
GPT54_CACHE_READ = 0.125

DEFAULT_MAX_TOKENS = 48_000  # raised: 16K -> 32K (voluptuous fix) -> 48K (marshmallow fields.py / jinja compiler.py)
DEFAULT_TIMEOUT_S = 300
DEFAULT_RETRIES = 4

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-5.4",
}


class LLMClient:
    """Unified LLM call. .call(instructions, cached_block) -> (response_text, usage_dict).

    usage_dict keys: input, output, cache_read, cache_write
    """

    def __init__(self, provider: str, model: str | None = None,
                 max_tokens: int = DEFAULT_MAX_TOKENS,
                 timeout: float = DEFAULT_TIMEOUT_S,
                 max_retries: int = DEFAULT_RETRIES):
        self.provider = provider
        self.model = model or DEFAULT_MODELS[provider]
        # Opt-in env-var override for max_tokens. Used by the local-calibration
        # bench (benchmarks/_internal/experiments/round_trip/local_calibration/) to
        # match commercial output budget against local Qwen's `num_predict` cap.
        # Production behavior is unchanged when the env var is unset.
        env_cap = os.environ.get("KAIZEN_LLM_MAX_TOKENS")
        if env_cap:
            try:
                max_tokens = int(env_cap)
            except ValueError:
                pass
        self.max_tokens = max_tokens
        if provider == "anthropic":
            from anthropic import Anthropic
            self._c = Anthropic(timeout=timeout, max_retries=max_retries)
        elif provider == "openai":
            from openai import OpenAI
            self._c = OpenAI(timeout=timeout, max_retries=max_retries)
        else:
            raise ValueError(f"unknown provider: {provider}")

    def call(self, instructions: str, cached_block: str = "") -> tuple[str, dict]:
        if self.provider == "anthropic":
            content = []
            if cached_block:
                content.append({"type": "text", "text": cached_block,
                                "cache_control": {"type": "ephemeral"}})
            content.append({"type": "text", "text": instructions})
            msg = self._c.messages.create(
                model=self.model, max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": content}])
            return (
                msg.content[0].text,
                {"input": msg.usage.input_tokens,
                 "output": msg.usage.output_tokens,
                 "cache_read": getattr(msg.usage, "cache_read_input_tokens", 0) or 0,
                 "cache_write": getattr(msg.usage, "cache_creation_input_tokens", 0) or 0},
            )
        # OpenAI: combine into single user message; auto-cache catches identical prefixes
        prompt = (cached_block + "\n\n" + instructions) if cached_block else instructions
        msg = self._c.chat.completions.create(
            model=self.model, max_completion_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}])
        details = getattr(msg.usage, "prompt_tokens_details", None)
        cached = (details.cached_tokens if details else 0) or 0
        return (
            msg.choices[0].message.content or "",
            {"input": msg.usage.prompt_tokens, "output": msg.usage.completion_tokens,
             "cache_read": cached, "cache_write": 0},
        )


def cost(provider: str, usage: dict) -> float:
    """Compute $ from a usage dict produced by LLMClient.call."""
    if provider == "anthropic":
        return (usage["input"] * SONNET_INPUT
                + usage["cache_read"] * SONNET_CACHE_READ
                + usage["cache_write"] * SONNET_CACHE_WRITE
                + usage["output"] * SONNET_OUTPUT) / 1_000_000
    fresh = usage["input"] - usage["cache_read"]
    return (fresh * GPT54_INPUT
            + usage["cache_read"] * GPT54_CACHE_READ
            + usage["output"] * GPT54_OUTPUT) / 1_000_000
