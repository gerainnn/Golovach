# Golovach

Telegram-бот с командой AI-агентов: оркестратор, два кодера, критик и судья.
Агенты спорят между собой, финальный ответ пропускает «слепой» judge.

## Архитектура

```
Telegram → Classifier ──┬── [general] → Orchestrator → Judge → ответ
                        │
                        └── [code]    → Orchestrator (план)
                                       → Coder A ╲
                                                   ╳  Debate (N раундов)
                                         Coder B ╱        ↑ Critic
                                       → Judge (слепой) → ответ
```

- **Провайдеры** подключаются через единый OpenAI-совместимый интерфейс
  (`base_url` + ключ). Поддерживается несколько провайдеров сразу с
  автоматическим fallback на случай сбоя/лимитов.
- **Роли агентов** мапятся на цепочки `(provider, model)` — можно легко
  дать Claude оркестратору, DeepSeek критику, GPT судье и т.д.

## Быстрый старт

```bash
cp .env.example .env
# заполни TELEGRAM_BOT_TOKEN и хотя бы одного провайдера

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Структура

| Файл            | Что делает                                               |
|-----------------|----------------------------------------------------------|
| `config.py`     | pydantic-settings, читает `.env`                         |
| `providers.py`  | `LLMProvider` (OpenAI-совместимый) + `Router` с fallback |
| `agents.py`     | Agent-классы и системные промпты                         |
| `pipeline.py`   | Classifier + debate loop + runner                        |
| `bot.py`        | aiogram-хендлеры                                         |
| `main.py`       | Сборка роутера и запуск                                  |

## Как расширять

- **Новый агент** (например, Tester или Frontend): добавь класс в `agents.py`,
  подключи в `pipeline.run_code`, добавь запись в `role_chain` в `main.py`.
- **Новый провайдер**: добавь переменные в `.env`/`config.py` и ещё одну
  ветку в `build_router()` в `main.py`.
- **Другие модели по ролям**: просто поменяй значения в `.env`.

## Замечания

- Провайдеры добавляют задержку и могут не пробрасывать всё
  (prompt caching, structured outputs, reasoning). Проверяй у своего провайдера.
- Rate-limits общие на аккаунт, а не на модель — не стоит гнать слишком
  много параллельных раундов без семафора.
