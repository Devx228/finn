"""Postgres-backed LLM cache and cost ledger."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from finn import db

# USD per 1M tokens (input, output) at the provider's PAID list price, so the ledger shows
# what the free usage would have cost. Filled from provider pricing pages when verified;
# unknown models log NULL rather than a guess. Local models cost nothing.
LIST_PRICE_PER_M: dict[tuple[str, str], tuple[float, float]] = {}


def list_price(provider: str | None, model: str | None, tin: int | None, tout: int | None):
    if provider == "ollama":
        return 0.0
    p = LIST_PRICE_PER_M.get((provider or "", model or ""))
    if p is None or tin is None or tout is None:
        return None
    return (tin * p[0] + tout * p[1]) / 1_000_000


class LLMStore:
    def cache_get(self, key: str) -> dict[str, Any] | None:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT provider, model, response FROM llm_cache WHERE key = %s", (key,)
            ).fetchone()
        return None if row is None else {"provider": row[0], "model": row[1], "response": row[2]}

    def cache_put(self, key: str, tier: str, provider: str, model: str, response: Any) -> None:
        with db.connection() as conn:
            conn.execute(
                "INSERT INTO llm_cache (key, tier, provider, model, response) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (key) DO NOTHING",
                (key, tier, provider, model, Jsonb(response)),
            )

    def log(
        self,
        *,
        tier,
        purpose,
        provider=None,
        model=None,
        input_tokens=None,
        output_tokens=None,
        cache_hit,
        latency_ms=None,
        ok,
        error=None,
    ) -> None:
        with db.connection() as conn:
            conn.execute(
                "INSERT INTO llm_calls (tier, provider, model, purpose, input_tokens, "
                "output_tokens, cache_hit, latency_ms, list_price_usd, ok, error) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    tier,
                    provider,
                    model,
                    purpose,
                    input_tokens,
                    output_tokens,
                    cache_hit,
                    latency_ms,
                    list_price(provider, model, input_tokens, output_tokens),
                    ok,
                    error,
                ),
            )
