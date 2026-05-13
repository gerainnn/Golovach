"""Оркестрация: classify → route → debate → judge.

Все вызовы LLM — последовательные (не параллельные), чтобы не упираться
в concurrency limits бесплатных провайдеров.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from agents import Classifier, Coder, Critic, Judge, Orchestrator
from providers import Router

log = logging.getLogger(__name__)


async def classify(router: Router, query: str) -> str:
    clf = Classifier(router)
    raw = (await clf.act(query)).strip().lower()
    return "code" if "code" in raw else "general"


async def stream_general(router: Router, query: str) -> AsyncIterator[str]:
    orch = Orchestrator(router)
    async for delta in orch.stream(query):
        yield delta


async def run_code(router: Router, query: str, rounds: int) -> str:
    orch = Orchestrator(router)
    coder_a = Coder(router, "A")
    coder_b = Coder(router, "B")
    critic = Critic(router)
    judge = Judge(router)

    plan = await orch.act(f"Декомпозируй задачу для команды разработчиков:\n{query}")

    # Последовательно — чтобы не получить 429 concurrency limit
    sol_a = await coder_a.act(f"ПЛАН:\n{plan}\n\nЗАДАЧА:\n{query}\n\nНапиши своё решение.")
    sol_b = await coder_b.act(f"ПЛАН:\n{plan}\n\nЗАДАЧА:\n{query}\n\nНапиши своё решение.")

    for _ in range(max(0, rounds)):
        crit_a = await critic.act(
            f"ЗАДАЧА:\n{query}\n\nРЕШЕНИЕ A:\n{sol_a}\n\nРЕШЕНИЕ B:\n{sol_b}\n\n"
            "Дай конкретную критику РЕШЕНИЯ A."
        )
        crit_b = await critic.act(
            f"ЗАДАЧА:\n{query}\n\nРЕШЕНИЕ A:\n{sol_a}\n\nРЕШЕНИЕ B:\n{sol_b}\n\n"
            "Дай конкретную критику РЕШЕНИЯ B."
        )
        sol_a = await coder_a.act(
            f"Твоё предыдущее решение:\n{sol_a}\n\n"
            f"Критика:\n{crit_a}\n\nПерепиши и улучши решение."
        )
        sol_b = await coder_b.act(
            f"Твоё предыдущее решение:\n{sol_b}\n\n"
            f"Критика:\n{crit_b}\n\nПерепиши и улучши решение."
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
