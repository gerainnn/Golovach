"""Оркестрация: классификация запроса → маршрутизация → debate → judge."""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from agents import Classifier, Coder, Critic, Judge, Orchestrator
from providers import Router

log = logging.getLogger(__name__)


async def classify(router: Router, query: str) -> str:
    """Возвращает 'code' или 'general'. Любые нестандартные ответы трактуем как 'general'."""
    clf = Classifier(router)
    raw = (await clf.act(query)).strip().lower()
    return "code" if "code" in raw else "general"


async def stream_general(router: Router, query: str) -> AsyncIterator[str]:
    """Для общих вопросов: один агент (Orchestrator) стримит ответ напрямую.
    Судья для коротких вопросов чаще всё портит, чем улучшает."""
    orch = Orchestrator(router)
    async for delta in orch.stream(query):
        yield delta


async def run_code(router: Router, query: str, rounds: int) -> str:
    """Debate pipeline для код-задач: план → 2 решения → критика → улучшение → judge."""
    orch = Orchestrator(router)
    coder_a = Coder(router, "A")
    coder_b = Coder(router, "B")
    critic = Critic(router)
    judge = Judge(router)

    plan = await orch.act(f"Декомпозируй задачу для команды разработчиков:\n{query}")

    sol_a, sol_b = await asyncio.gather(
        coder_a.act(f"ПЛАН:\n{plan}\n\nЗАДАЧА:\n{query}\n\nНапиши своё решение."),
        coder_b.act(f"ПЛАН:\n{plan}\n\nЗАДАЧА:\n{query}\n\nНапиши своё решение."),
    )

    for _ in range(max(0, rounds)):
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
        sol_a, sol_b = await asyncio.gather(
            coder_a.act(
                f"Твоё предыдущее решение:\n{sol_a}\n\n"
                f"Критика:\n{crit_a}\n\nПерепиши и улучши решение."
            ),
            coder_b.act(
                f"Твоё предыдущее решение:\n{sol_b}\n\n"
                f"Критика:\n{crit_b}\n\nПерепиши и улучши решение."
            ),
        )

    # Judge — слепой: не видит дебатов, только финальные варианты и ТЗ
    final = await judge.act(
        f"ЗАДАЧА ПОЛЬЗОВАТЕЛЯ:\n{query}\n\n"
        f"ВАРИАНТ A:\n{sol_a}\n\n"
        f"ВАРИАНТ B:\n{sol_b}\n\n"
        "Верни пользователю лучший ответ (или мерж). Только итог, без мета."
    )
    return final


async def run(router: Router, query: str, rounds: int = 1) -> AsyncIterator[str]:
    """Универсальный runner. Возвращает async-итератор дельт.
    Для 'general' стримит напрямую; для 'code' дебат — отдаёт итог одним куском."""
    kind = await classify(router, query)
    log.info("Query classified as: %s", kind)
    if kind == "general":
        async for delta in stream_general(router, query):
            yield delta
        return
    final = await run_code(router, query, rounds)
    yield final
