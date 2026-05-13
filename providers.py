"""Слой провайдеров и роутер с fallback.

Любой OpenAI-совместимый провайдер (Kiro, Groq, Z.AI, OpenRouter, Together и т.д.)
подключается через один и тот же класс LLMProvider — отличаются только base_url и ключ.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

log = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: str


class LLMProvider:
    def __init__(self, cfg: ProviderConfig, timeout: int = 120):
        self.cfg = cfg
        self.client = AsyncOpenAI(
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            timeout=timeout,
        )

    async def complete(self, model: str, messages: list[dict], **kwargs: Any) -> str:
        import asyncio as _aio
        for attempt in range(5):
            try:
                resp = await self.client.chat.completions.create(
                    model=model, messages=messages, **kwargs
                )
                return resp.choices[0].message.content or ""
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower() or "concurrency" in str(e).lower():
                    wait = 3 * (attempt + 1)
                    log.warning("Rate limited (attempt %d), waiting %ds...", attempt+1, wait)
                    await _aio.sleep(wait)
                else:
                    raise
        raise RuntimeError(f"Rate limited after 5 retries for model {model}")

    async def stream(
        self, model: str, messages: list[dict], **kwargs: Any
    ) -> AsyncIterator[str]:
        """Стриминг с retry при 429."""
        import asyncio as _aio
        for attempt in range(5):
            try:
                stream = await self.client.chat.completions.create(
                    model=model, messages=messages, stream=True, **kwargs
                )
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
                return  # success
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower() or "concurrency" in str(e).lower():
                    wait = 3 * (attempt + 1)
                    log.warning("Stream rate limited (attempt %d), waiting %ds...", attempt+1, wait)
                    await _aio.sleep(wait)
                else:
                    raise
        raise RuntimeError(f"Stream rate limited after 5 retries for model {model}")


class Router:
    """Маппит роль агента на цепочку (provider, model) с fallback."""

    def __init__(
        self,
        providers: dict[str, LLMProvider],
        role_chain: dict[str, list[tuple[str, str]]],
    ):
        if not providers:
            raise ValueError("No providers configured. Set at least one API key in .env")
        self.providers = providers
        self.role_chain = role_chain

    def set_role_model(self, role: str, full_string: str) -> None:
        """Меняет модель для роли на лету. full_string = 'provider_name/model' или просто 'model'."""
        parts = full_string.split("/", 1)
        if len(parts) == 2:
            provider_name, model = parts[0], parts[1]
        else:
            provider_name = next(iter(self.providers))
            model = full_string
        self.role_chain[role] = [(provider_name, model)]

    def get_role_model(self, role: str) -> str:
        chain = self.role_chain.get(role) or []
        return chain[0][1] if chain else "?"

    async def call(self, role: str, messages: list[dict], **kwargs: Any) -> str:
        chain = self.role_chain.get(role)
        if not chain:
            raise ValueError(f"No chain configured for role '{role}'")

        last_err: Exception | None = None
        for provider_name, model in chain:
            provider = self.providers.get(provider_name)
            if provider is None:
                continue
            try:
                return await provider.complete(model, messages, **kwargs)
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "Provider '%s' failed for role '%s' (model=%s): %s",
                    provider_name, role, model, e,
                )
                last_err = e
                continue
        raise RuntimeError(f"All providers failed for role '{role}'") from last_err

    async def stream(
        self, role: str, messages: list[dict], **kwargs: Any
    ) -> AsyncIterator[str]:
        """Стриминг с fallback: если первый провайдер упал ДО первой дельты —
        пробуем следующего. Если упал посередине — ошибку отдаём наверх."""
        chain = self.role_chain.get(role)
        if not chain:
            raise ValueError(f"No chain configured for role '{role}'")

        last_err: Exception | None = None
        for provider_name, model in chain:
            provider = self.providers.get(provider_name)
            if provider is None:
                continue
            try:
                got_any = False
                async for delta in provider.stream(model, messages, **kwargs):
                    got_any = True
                    yield delta
                if got_any:
                    return
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "Stream provider '%s' failed for role '%s' (model=%s): %s",
                    provider_name, role, model, e,
                )
                last_err = e
                continue
        raise RuntimeError(f"All stream providers failed for role '{role}'") from last_err
