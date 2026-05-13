"""Оркестрация: classify → route → debate → judge.

Параллельность определяется по supports_parallel флагу провайдеров.
Если оба агента на провайдере с parallel=True — запускаем параллельно.
Иначе — последовательно, чтобы не получить 429.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from agents import Classifier, Coder, Critic, Judge, Orchestrator
from config import load_providers_config
from providers import Router

log = logging.getLogger(__name__)


def _can_parallel(router: Router, role_a: str, role_b: str) -> bool:
    """Проверяет можно ли запускать две роли параллельно.
    Если они на разных провайдерах — всегда можно.
    Если на одном — только если supports_parallel=True."""
    chain_a = router.role_chain.get(role_a, [])
    chain_b = router.role_chain.get(role_b, [])
    if not chain_a or not chain_b:
        return False
    prov_a = chain_a[0][0]
    prov_b = chain_b[0][0]
    if prov_a != prov_b:
        return True  # разные провайдеры — параллелим
    # Один провайдер — смотрим флаг
    providers_cfg = load_providers_config()
    for p in providers_cfg:
        if p.get("name") == prov_a:
            return p.get("supports_parallel", True)
    return True


async def classify(router: Router, query: str) -> str:
    clf = Classifier(router)
    raw = (await clf.act(query)).strip().lower()
    return "code" if "code" in raw else "general"


async def stream_general(router: Router, query: str) -> AsyncIterator[str]:
    orch = Orchestrator(router)
    async for delta in orch.stream(query):
        yield delta


async def _dual_call(router: Router, role_a: str, role_b: str, coro_a, coro_b):
    """Вызывает два корутина параллельно или последовательно в зависимости от провайдера."""
    if _can_parallel(router, role_a, role_b):
        return await asyncio.gather(coro_a, coro_b)
    else:
        res_a = await coro_a
        res_b = await coro_b
        return res_a, res_b


async def run_code(router: Router, query: str, rounds: int) -> str:
    orch = Orchestrator(router)
    coder_a = Coder(router, "A")
    coder_b = Coder(router, "B")
    critic = Critic(router)
    judge = Judge(router)

    plan = await orch.act(f"Декомпозируй задачу для команды разработчиков:\n{query}")

    # Кодеры — параллельно если можно
    sol_a, sol_b = await _dual_call(
        router, "coder_a", "coder_b",
        coder_a.act(f"ПЛАН:\n{plan}\n\nЗАДАЧА:\n{query}\n\nНапиши своё решение."),
        coder_b.act(f"ПЛАН:\n{plan}\n\nЗАДАЧА:\n{query}\n\nНапиши своё решение."),
    )

    for _ in range(max(0, rounds)):
        # Критик — два вызова одной роли (critic), проверяем параллельность самого с собой
        if _can_parallel(router, "critic", "critic"):
            crit_a, crit_b = await asyncio.gather(
                critic.act(
                    f"ЗАДАЧА:\n{query}\n\nРЕШЕНИЕ A:\n{sol_a}\n\nРЕШЕНИЕ B:\n{sol_b}\n\n"
                    "Дай конкретную критику РЕШЕНИЯ A."
                ),
                critic.act(
                    f"ЗАДАЧА:\n{query}\n\nРЕШЕНИЕ A:\n{sol_a}\n\nРЕШЕНИЕ B:\n{sol_b}\n\n"
                    "Дай конкретную критику РЕШЕНИЯ B."
                ),
            )
        else:
            crit_a = await critic.act(
                f"ЗАДАЧА:\n{query}\n\nРЕШЕНИЕ A:\n{sol_a}\n\nРЕШЕНИЕ B:\n{sol_b}\n\n"
                "Дай конкретную критику РЕШЕНИЯ A."
            )
            crit_b = await critic.act(
                f"ЗАДАЧА:\n{query}\n\nРЕШЕНИЕ A:\n{sol_a}\n\nРЕШЕНИЕ B:\n{sol_b}\n\n"
                "Дай конкретную критику РЕШЕНИЯ B."
            )

        # Улучшение — параллельно если можно
        sol_a, sol_b = await _dual_call(
            router, "coder_a", "coder_b",
            coder_a.act(
                f"Твоё предыдущее решение:\n{sol_a}\n\n"
                f"Критика:\n{crit_a}\n\nПерепиши и улучши решение."
            ),
            coder_b.act(
                f"Твоё предыдущее решение:\n{sol_b}\n\n"
                f"Критика:\n{crit_b}\n\nПерепиши и улучши решение."
            ),
        )

    final = await judge.act(
        f"ЗАДАЧА ПОЛЬЗОВАТЕЛЯ:\n{query}\n\n"
        f"ВАРИАНТ A:\n{sol_a}\n\n"
        f"ВАРИАНТ B:\n{sol_b}\n\n"
        "Верни пользователю лучший ответ (или мерж). Только итог, без мета."
    )
    return final


async def run(router: Router, query: str, rounds: int = 1) -> AsyncIterator[str]:
    kind = await classify(router, query)
    log.info("Query classified as: %s", kind)
    if kind == "general":
        async for delta in stream_general(router, query):
            yield delta
        return
    final = await run_code(router, query, rounds)
    yield final
