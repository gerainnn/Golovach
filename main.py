"""Точка входа: собирает провайдеров из providers.json, роутер, запускает бота."""
from __future__ import annotations

import asyncio
import logging

from bot import start_bot
from config import settings, load_providers_config, load_infra_settings
from providers import LLMProvider, ProviderConfig, Router

ROLES = ("classifier", "orchestrator", "coder_a", "coder_b", "critic", "judge")


def parse_admin_ids(raw: str) -> set[int]:
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit() or (part.startswith("-") and part[1:].isdigit()):
            out.add(int(part))
    return out


def build_router() -> Router:
    raw_providers = load_providers_config()
    if not raw_providers:
        raise RuntimeError(
            "Нет настроенных провайдеров. Запусти: python setup.py (или python configure.py)"
        )

    infra = load_infra_settings()
    timeout = infra.get("request_timeout", settings.request_timeout)

    # Создаём LLMProvider для каждого провайдера из providers.json
    providers: dict[str, LLMProvider] = {}
    for p in raw_providers:
        name = p.get("name", "")
        base_url = p.get("base_url", "")
        api_key = p.get("api_key", "")
        if name and base_url and api_key:
            providers[name] = LLMProvider(
                ProviderConfig(name, base_url, api_key),
                timeout=timeout,
            )

    if not providers:
        raise RuntimeError("Провайдеры в providers.json есть, но ни один не валиден.")

    # Строим role_chain: для каждой роли берём "provider_name/model" из .env
    # Формат значения: "provider_name/model_name" (первый / отделяет имя провайдера)
    role_chain: dict[str, list[tuple[str, str]]] = {}
    for role in ROLES:
        full_string = getattr(settings, f"{role}_model", "")
        if not full_string:
            # Если роль не настроена — берём первого провайдера и пустую модель (упадёт при вызове)
            continue
        parts = full_string.split("/", 1)
        if len(parts) == 2:
            provider_name, model = parts[0], parts[1]
        else:
            # Нет '/' — берём первого провайдера
            provider_name = next(iter(providers))
            model = full_string
        role_chain[role] = [(provider_name, model)]

    if not role_chain:
        raise RuntimeError(
            "Ни одна роль не настроена. Запусти python configure.py и назначь модели."
        )

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
