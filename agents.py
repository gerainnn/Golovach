"""Агенты. Промпты вынесены в prompts.py — правь их там."""
from __future__ import annotations

from typing import AsyncIterator

from prompts import PROMPTS
from providers import Router


class Agent:
    """Базовый агент: системный промпт + роль для роутинга провайдеров."""

    def __init__(self, router: Router, role: str, system_prompt: str, name: str = ""):
        self.router = router
        self.role = role
        self.system_prompt = system_prompt
        self.name = name

    def _build_messages(
        self, user_message: str, context: list[dict] | None = None
    ) -> list[dict]:
        messages: list[dict] = [{"role": "system", "content": self.system_prompt}]
        if context:
            messages.extend(context)
        messages.append({"role": "user", "content": user_message})
        return messages

    async def act(self, user_message: str, context: list[dict] | None = None) -> str:
        return await self.router.call(self.role, self._build_messages(user_message, context))

    async def stream(
        self, user_message: str, context: list[dict] | None = None
    ) -> AsyncIterator[str]:
        async for delta in self.router.stream(
            self.role, self._build_messages(user_message, context)
        ):
            yield delta


class Classifier(Agent):
    def __init__(self, router: Router):
        super().__init__(router, "classifier", PROMPTS["classifier"])


class Orchestrator(Agent):
    def __init__(self, router: Router):
        super().__init__(router, "orchestrator", PROMPTS["orchestrator"])


class Coder(Agent):
    """Кодер. name='A'|'B' — определяет роль ('coder_a' / 'coder_b') и, значит, модель."""

    def __init__(self, router: Router, name: str):
        role = f"coder_{name.lower()}"
        sys = PROMPTS["coder"] + f"\n\nТвоё кодовое имя в команде: {name}."
        super().__init__(router, role, sys, name=name)


class Critic(Agent):
    def __init__(self, router: Router):
        super().__init__(router, "critic", PROMPTS["critic"])


class Judge(Agent):
    def __init__(self, router: Router):
        super().__init__(router, "judge", PROMPTS["judge"])
