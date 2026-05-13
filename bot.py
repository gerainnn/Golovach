"""Telegram-бот на aiogram v3 со стримингом и командой /settings."""
from __future__ import annotations

import asyncio
import logging
import time

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message

from config import settings
from pipeline import run
from providers import Router

log = logging.getLogger(__name__)

MAX_TG_LEN = 4000           # безопасный лимит на одно TG-сообщение
EDIT_INTERVAL_SEC = 1.2     # как часто обновляем «печатающееся» сообщение
ROLES = ("classifier", "orchestrator", "coder_a", "coder_b", "critic", "judge")


def _is_admin(user_id: int | None, admin_ids: set[int]) -> bool:
    if not admin_ids:
        return True  # если список пуст — доступ у всех
    return user_id is not None and user_id in admin_ids


async def _safe_edit(msg: Message, text: str) -> None:
    """edit_text, игнорируя 'message is not modified' и обрезая по лимиту."""
    text = text[:MAX_TG_LEN] if len(text) > MAX_TG_LEN else text
    if not text:
        return
    try:
        await msg.edit_text(text)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        raise


def build_dispatcher(router: Router, admin_ids: set[int]) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def cmd_start(m: Message) -> None:
        await m.answer(
            "Привет. Я AI-команда: оркестратор, два кодера, критик и судья.\n"
            "Задай вопрос или опиши задачу — общие вопросы стримятся, "
            "код-задачи проходят через дебат.\n\n"
            "/settings — посмотреть/изменить модели и параметры.\n"
            "/ping — проверить, что бот жив."
        )

    @dp.message(Command("ping"))
    async def cmd_ping(m: Message) -> None:
        await m.answer("pong")

    @dp.message(Command("settings"))
    async def cmd_settings(m: Message) -> None:
        if not _is_admin(m.from_user.id if m.from_user else None, admin_ids):
            await m.answer("Настройки доступны только админам (ADMIN_IDS в .env).")
            return

        args = (m.text or "").split(maxsplit=2)
        # /settings — показать текущие
        if len(args) == 1:
            lines = ["Текущая конфигурация:\n"]
            for role in ROLES:
                lines.append(f"• {role}: `{router.get_role_model(role)}`")
            lines.append(f"\n• debate_rounds: {settings.debate_rounds}")
            lines.append("\nИзменить модель:\n`/settings <role> <model>`")
            lines.append("Пример: `/settings judge openai/gpt-5`")
            lines.append("Раунды дебата: `/settings rounds 2`")
            await m.answer("\n".join(lines), parse_mode="Markdown")
            return

        # /settings rounds N
        if len(args) >= 3 and args[1].lower() == "rounds":
            try:
                n = int(args[2])
                if n < 0 or n > 5:
                    raise ValueError("range")
                settings.debate_rounds = n
                await m.answer(f"debate_rounds = {n}")
            except ValueError:
                await m.answer("Ожидаю целое число 0..5")
            return

        # /settings <role> <model>
        if len(args) < 3:
            await m.answer("Формат: `/settings <role> <model>`", parse_mode="Markdown")
            return
        role, model = args[1].lower(), args[2].strip()
        if role not in ROLES:
            await m.answer(f"Неизвестная роль. Доступные: {', '.join(ROLES)}")
            return
        router.set_role_model(role, model)
        await m.answer(f"OK. {role} → `{model}`", parse_mode="Markdown")

    @dp.message(F.text)
    async def on_text(m: Message) -> None:
        placeholder = await m.answer("Думаю...")
        buffer = ""
        last_edit = 0.0

        try:
            async for delta in run(router, m.text, rounds=settings.debate_rounds):
                buffer += delta
                now = time.monotonic()
                # апдейтим сообщение не чаще, чем раз в EDIT_INTERVAL_SEC,
                # и только пока умещаемся в один TG-месседж
                if now - last_edit >= EDIT_INTERVAL_SEC and len(buffer) <= MAX_TG_LEN:
                    await _safe_edit(placeholder, buffer)
                    last_edit = now
        except Exception as e:  # noqa: BLE001
            log.exception("Pipeline error")
            await _safe_edit(placeholder, f"Ошибка: {e}")
            return

        if not buffer:
            await _safe_edit(placeholder, "(пустой ответ)")
            return

        # Финальная отправка: если влезает — просто редактируем; иначе шлём частями
        if len(buffer) <= MAX_TG_LEN:
            await _safe_edit(placeholder, buffer)
        else:
            try:
                await placeholder.delete()
            except Exception:  # noqa: BLE001
                pass
            for i in range(0, len(buffer), MAX_TG_LEN):
                await m.answer(buffer[i : i + MAX_TG_LEN])
                await asyncio.sleep(0.05)

    return dp


async def start_bot(router: Router, admin_ids: set[int]) -> None:
    bot = Bot(token=settings.telegram_bot_token)
    dp = build_dispatcher(router, admin_ids)
    log.info("Bot started. Admins: %s", admin_ids or "ANY")
    await dp.start_polling(bot)
