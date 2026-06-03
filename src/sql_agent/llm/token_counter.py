"""Token counting and cost tracking per LLM call.

Owner: Asad.

Two jobs:
  1. Estimate how many tokens a prompt + completion consume.
  2. Price those tokens against the OCI Generative AI model used, so the
     benchmark can report a "token cost per request" metric and the model
     router has a number to optimise against.

Token counting
--------------
OCI's hosted models (Cohere Command, Meta Llama) do not ship a local tokenizer
we can rely on offline. If the OCI SDK or a tokenizer is wired in later, set
`TokenCounter(tokenizer=...)`. Otherwise we use a fast heuristic (~4 chars per
token, with a word-count floor) that is accurate to within ~10-15% for English
+ SQL - good enough for relative cost comparisons across runs.

Pricing
-------
PRICING is expressed in USD per 1,000 tokens, split into input (prompt) and
output (completion) rates. **These are placeholders - confirm against the live
OCI Generative AI pricing page before quoting a number on a slide.** Override
per-deployment via settings / env rather than editing this file.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel, Field

from sql_agent.core.models import Metric


class BudgetExceededError(RuntimeError):
    """Raised when a request exceeds its configured token-cost or call budget.

    The orchestrator can catch this to back off / degrade gracefully instead of
    looping near AGENT_MAX_RETRIES and exploding the cloud bill.
    """


@dataclass(frozen=True)
class ModelPrice:
    """USD price per 1,000 tokens for a model."""

    input_per_1k: float
    output_per_1k: float


# Placeholder rate card - UPDATE from https://www.oracle.com/.../generative-ai pricing.
# Keys are OCI GenAI model ids (or friendly aliases we map in the router).
PRICING: dict[str, ModelPrice] = {
    "cohere.command-r-08-2024": ModelPrice(0.00050, 0.00150),
    "cohere.command-r-plus-08-2024": ModelPrice(0.00300, 0.01500),
    "meta.llama-3.1-70b-instruct": ModelPrice(0.00060, 0.00060),
    "meta.llama-3.1-405b-instruct": ModelPrice(0.00530, 0.01600),
    # Friendly aliases used by the model router (small/large tiers).
    "small": ModelPrice(0.00050, 0.00150),
    "large": ModelPrice(0.00300, 0.01500),
}

# Used when a model id is unknown - priced at the most expensive known tier so
# cost is never silently under-reported.
_FALLBACK_PRICE = ModelPrice(0.00300, 0.01500)

_WORD_RE = re.compile(r"\w+|[^\w\s]")


def estimate_tokens(text: str) -> int:
    """Heuristic token count for `text` (no external tokenizer needed)."""
    if not text:
        return 0
    by_chars = math.ceil(len(text) / 4)
    by_words = len(_WORD_RE.findall(text))
    # Take the larger of the two estimates; punctuation-heavy SQL trends high.
    return max(by_chars, by_words, 1)


class TokenUsage(BaseModel):
    """Tokens and cost for a single LLM call."""

    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    cost_usd: float = 0.0


def price_usage(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return the USD cost of a call given token counts."""
    price = PRICING.get(model, _FALLBACK_PRICE)
    return round(
        prompt_tokens / 1000.0 * price.input_per_1k
        + completion_tokens / 1000.0 * price.output_per_1k,
        8,
    )


@dataclass
class TokenCounter:
    """Counts + prices tokens, accumulating across the calls of one request/run.

    tokenizer: optional callable(text) -> int to replace the heuristic with a
               real tokenizer (e.g. the OCI/Cohere tokenizer) when available.
    """

    tokenizer: Callable[[str], int] | None = None
    usages: list[TokenUsage] = field(default_factory=list)
    # Cost-aware guardrails. None = unlimited. The orchestrator sets these per
    # request (e.g. budget_usd from settings, max_calls ~ AGENT_MAX_RETRIES + a
    # margin) and calls check() inside its loop.
    budget_usd: float | None = None
    max_calls: int | None = None

    def _count(self, text: str) -> int:
        return self.tokenizer(text) if self.tokenizer else estimate_tokens(text)

    def record(self, model: str, prompt: str, completion: str = "") -> TokenUsage:
        """Count + price one LLM call, store it, and return the usage."""
        p = self._count(prompt)
        c = self._count(completion)
        usage = TokenUsage(
            model=model,
            prompt_tokens=p,
            completion_tokens=c,
            cost_usd=price_usage(model, p, c),
        )
        self.usages.append(usage)
        return usage

    def record_counts(self, model: str, prompt_tokens: int, completion_tokens: int) -> TokenUsage:
        """Record a call when the provider already reported exact token counts."""
        usage = TokenUsage(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=price_usage(model, prompt_tokens, completion_tokens),
        )
        self.usages.append(usage)
        return usage

    @property
    def total_tokens(self) -> int:
        return sum(u.total_tokens for u in self.usages)

    @property
    def total_cost_usd(self) -> float:
        return round(sum(u.cost_usd for u in self.usages), 8)

    def reset(self) -> None:
        self.usages.clear()

    @property
    def n_calls(self) -> int:
        return len(self.usages)

    @property
    def remaining_usd(self) -> float | None:
        """USD left in the budget, or None if no budget is set."""
        if self.budget_usd is None:
            return None
        return round(self.budget_usd - self.total_cost_usd, 8)

    @property
    def over_budget(self) -> bool:
        """True if either the cost or the call budget has been exceeded."""
        if self.budget_usd is not None and self.total_cost_usd > self.budget_usd:
            return True
        if self.max_calls is not None and self.n_calls > self.max_calls:
            return True
        return False

    def would_exceed(self, next_cost_usd: float = 0.0) -> bool:
        """True if making one more call (costing ~next_cost_usd) would breach a limit."""
        if self.max_calls is not None and self.n_calls + 1 > self.max_calls:
            return True
        if self.budget_usd is not None and self.total_cost_usd + next_cost_usd > self.budget_usd:
            return True
        return False

    def check(self) -> None:
        """Raise BudgetExceededError if a limit has already been breached."""
        if self.over_budget:
            raise BudgetExceededError(
                f"token budget exceeded: ${self.total_cost_usd} spent over "
                f"{self.n_calls} calls (budget=${self.budget_usd}, max_calls={self.max_calls})"
            )

    def as_metric(self) -> Metric:
        """Summarise accumulated cost as a benchmark Metric."""
        return Metric(
            name="token_cost_usd",
            value=self.total_cost_usd,
            unit="usd",
            detail=f"{self.total_tokens} tokens over {len(self.usages)} calls",
        )
