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
        resp = await self.client.chat.completions.create(
            model=model, messages=messages, **kwargs
        )
        return resp.choices[0].message.content or ""

    async def stream(
        self, model: str, messages: list[dict], **kwargs: Any
    ) -> AsyncIterator[str]:
        """Стриминг. Возвращает дельты текста по мере генерации."""
        stream = await self.client.chat.completions.create(
            model=model, messages=messages, stream=True, **kwargs
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


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

    def set_role_model(self, role: str, primary_model: str, free_fallback: str | None) -> None:
        """Меняет модель для роли на лету (используется /settings)."""
        primary_name = "kiro" if "kiro" in self.providers else "free"
        chain: list[tuple[str, str]] = [(primary_name, primary_model)]
        if free_fallback and "free" in self.providers and primary_name != "free":
            chain.append(("free", free_fallback))
        self.role_chain[role] = chain

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
