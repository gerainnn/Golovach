"""Точка входа: собирает провайдеров, роутер, запускает бота."""
from __future__ import annotations

import asyncio
import logging

from bot import start_bot
from config import settings
from providers import LLMProvider, ProviderConfig, Router


def parse_admin_ids(raw: str) -> set[int]:
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit() or (part.startswith("-") and part[1:].isdigit()):
            out.add(int(part))
    return out


def build_router() -> Router:
    providers: dict[str, LLMProvider] = {}

    if settings.kiro_api_key and settings.kiro_base_url:
        providers["kiro"] = LLMProvider(
            ProviderConfig("kiro", settings.kiro_base_url, settings.kiro_api_key),
            timeout=settings.request_timeout,
        )
    if settings.free_api_key and settings.free_base_url:
        providers["free"] = LLMProvider(
            ProviderConfig("free", settings.free_base_url, settings.free_api_key),
            timeout=settings.request_timeout,
        )

    if not providers:
        raise RuntimeError(
            "Нужен хотя бы один провайдер. Заполни KIRO_* или FREE_* в .env"
        )

    primary = "kiro" if "kiro" in providers else "free"
    has_fallback = "free" in providers and primary != "free"

    def chain(primary_model: str) -> list[tuple[str, str]]:
        out = [(primary, primary_model)]
        if has_fallback:
            out.append(("free", settings.free_fallback_model))
        return out

    role_chain = {
        "classifier": chain(settings.classifier_model),
        "orchestrator": chain(settings.orchestrator_model),
        "coder_a": chain(settings.coder_a_model),
        "coder_b": chain(settings.coder_b_model),
        "critic": chain(settings.critic_model),
        "judge": chain(settings.judge_model),
    }
    return Router(providers, role_chain)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    router = build_router()
    admin_ids = parse_admin_ids(settings.admin_ids)
    await start_bot(router, admin_ids)


if __name__ == "__main__":
    asyncio.run(main())
