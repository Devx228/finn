"""Provider-agnostic LLM router (spec §6). Every backend speaks the OpenAI chat API.

Tiers map to an ordered list of `provider:model` entries from env (LLM_TIER_<TIER>), e.g.
    LLM_TIER_BULK=ollama:qwen2.5:7b,gemini:gemini-2.5-flash-lite
A provider without an API key is skipped (Ollama needs none). On 429 / 5xx / timeout the router
backs off once, then falls to the next entry. Output is strict JSON validated against a pydantic
model, with one repair retry. Results are cached by content hash; every call (hit or miss,
success or failure) is written to the llm_calls ledger. Business logic never names a model.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from finn.config import get_settings

T = TypeVar("T", bound=BaseModel)

PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama": {"base_url_setting": "ollama_base_url", "key_setting": None},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "key_setting": "groq_api_key"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "key_setting": "openrouter_api_key"},
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_setting": "gemini_api_key",
    },
}

# Local default for every tier: the app runs with no keys at all.
DEFAULT_TIERS = {
    "BULK": "ollama:qwen2.5-7b-8k",
    "REASON": "ollama:qwen2.5-7b-8k",
    "VISION": "",
}

# Requests per minute per provider (free-tier figures from DECISIONS.md; override by env
# LLM_RPM_<PROVIDER>). Ollama is local: no limit beyond the GPU.
DEFAULT_RPM = {"ollama": 0, "groq": 30, "openrouter": 20, "gemini": 5}


@dataclass(frozen=True)
class Route:
    provider: str
    model: str


class LLMUnavailable(RuntimeError):
    pass


class ChatBackend(Protocol):
    def chat(
        self, route: Route, messages: list[dict], schema: dict | None, timeout: float
    ) -> tuple[str, int | None, int | None]:
        """Return (content, input_tokens, output_tokens). Raise RetryableError on 429/5xx."""
        ...


class RetryableError(RuntimeError):
    pass


def parse_routes(spec: str) -> list[Route]:
    out = []
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        provider, _, model = part.partition(":")
        if provider not in PROVIDERS or not model:
            raise ValueError(f"bad route {part!r}; expected provider:model")
        out.append(Route(provider, model))
    return out


def tier_routes(tier: str) -> list[Route]:
    spec = os.environ.get(f"LLM_TIER_{tier}", DEFAULT_TIERS.get(tier, ""))
    return [r for r in parse_routes(spec) if provider_available(r.provider)]


def provider_available(provider: str) -> bool:
    key_setting = PROVIDERS[provider]["key_setting"]
    return key_setting is None or bool(getattr(get_settings(), key_setting))


class OpenAIBackend:
    """Real backend over the openai SDK (OpenAI-compatible endpoints)."""

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}

    def _client(self, provider: str):
        if provider not in self._clients:
            from openai import OpenAI

            cfg, s = PROVIDERS[provider], get_settings()
            base = cfg.get("base_url") or getattr(s, cfg["base_url_setting"])
            key = getattr(s, cfg["key_setting"]) if cfg["key_setting"] else "ollama"
            self._clients[provider] = OpenAI(base_url=base, api_key=key, max_retries=0)
        return self._clients[provider]

    def chat(self, route, messages, schema, timeout):
        import openai

        kwargs: dict[str, Any] = {"model": route.model, "messages": messages, "temperature": 0}
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "out", "schema": schema, "strict": False},
            }
        try:
            r = self._client(route.provider).chat.completions.create(timeout=timeout, **kwargs)
        except openai.RateLimitError as e:
            raise RetryableError(f"429 from {route.provider}") from e
        except openai.APIStatusError as e:
            if e.status_code >= 500:
                raise RetryableError(f"{e.status_code} from {route.provider}") from e
            raise
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            raise RetryableError(f"{type(e).__name__} from {route.provider}") from e
        u = r.usage
        return (
            r.choices[0].message.content or "",
            u.prompt_tokens if u else None,
            u.completion_tokens if u else None,
        )


@dataclass
class CallResult:
    data: BaseModel
    provider: str
    model: str
    cache_hit: bool


@dataclass
class Router:
    backend: ChatBackend = field(default_factory=OpenAIBackend)
    store: Any = None  # finn.llm.store.LLMStore; None = no cache, no ledger (tests)
    timeout: float = 180.0
    sleep: Any = time.sleep
    _recent: dict[str, deque] = field(default_factory=dict)

    @staticmethod
    def cache_key(tier: str, prompt_version: str, payload: Any) -> str:
        body = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        input_hash = hashlib.sha256(body.encode()).hexdigest()
        return hashlib.sha256(f"{tier}|{prompt_version}|{input_hash}".encode()).hexdigest()

    def _throttle(self, provider: str) -> None:
        rpm = int(os.environ.get(f"LLM_RPM_{provider.upper()}", DEFAULT_RPM.get(provider, 0)))
        if rpm <= 0:
            return
        q = self._recent.setdefault(provider, deque())
        now = time.monotonic()
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= rpm:
            self.sleep(60 - (now - q[0]) + 0.1)
        q.append(time.monotonic())

    def call(
        self,
        tier: str,
        purpose: str,
        prompt_version: str,
        system: str,
        user: str,
        out: type[T],
        cache_payload: Any | None = None,
    ) -> CallResult:
        key = self.cache_key(tier, prompt_version, cache_payload if cache_payload is not None else user)
        if self.store is not None:
            hit = self.store.cache_get(key)
            if hit is not None:
                self.store.log(
                    tier=tier,
                    purpose=purpose,
                    provider=hit["provider"],
                    model=hit["model"],
                    cache_hit=True,
                    ok=True,
                )
                return CallResult(out.model_validate(hit["response"]), hit["provider"], hit["model"], True)

        routes = tier_routes(tier)
        if not routes:
            raise LLMUnavailable(f"no available provider for tier {tier}")
        schema = out.model_json_schema()
        errors = []
        for route in routes:
            messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
            for _attempt in range(2):  # second pass = repair retry after invalid JSON
                self._throttle(route.provider)
                t0 = time.monotonic()
                try:
                    content, tin, tout = self.backend.chat(route, messages, schema, self.timeout)
                except RetryableError as e:
                    self._log(tier, purpose, route, None, None, t0, False, str(e))
                    errors.append(str(e))
                    self.sleep(5)
                    break  # next provider
                try:
                    data = out.model_validate(json.loads(_strip_fences(content)))
                except (json.JSONDecodeError, ValidationError) as e:
                    self._log(tier, purpose, route, tin, tout, t0, False, f"invalid: {e}"[:300])
                    errors.append(f"{route.provider}: invalid output")
                    messages += [
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": f"That was not valid against the schema: "
                            f"{str(e)[:400]}. Reply with corrected JSON only.",
                        },
                    ]
                    continue
                self._log(tier, purpose, route, tin, tout, t0, True, None)
                if self.store is not None:
                    self.store.cache_put(key, tier, route.provider, route.model, data.model_dump(mode="json"))
                return CallResult(data, route.provider, route.model, False)
        raise LLMUnavailable(f"tier {tier} failed on every provider: {errors}")

    def _log(self, tier, purpose, route, tin, tout, t0, ok, error):
        if self.store is None:
            return
        self.store.log(
            tier=tier,
            purpose=purpose,
            provider=route.provider,
            model=route.model,
            input_tokens=tin,
            output_tokens=tout,
            cache_hit=False,
            latency_ms=int((time.monotonic() - t0) * 1000),
            ok=ok,
            error=error,
        )


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0]
    return s.strip()
