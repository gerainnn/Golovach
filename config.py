"""Конфигурация. Все секреты и настройки берутся из .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str

    # Провайдер 1 (основной)
    kiro_api_key: str = ""
    kiro_base_url: str = ""

    # Провайдер 2 (бесплатный fallback)
    free_api_key: str = ""
    free_base_url: str = ""

    # Модели по ролям
    classifier_model: str = "openai/gpt-4o-mini"
    orchestrator_model: str = "anthropic/claude-sonnet-4.5"
    coder_a_model: str = "anthropic/claude-sonnet-4.5"
    coder_b_model: str = "openai/gpt-5"
    critic_model: str = "deepseek/deepseek-v3.2"
    judge_model: str = "openai/gpt-5"
    free_fallback_model: str = "llama-3.3-70b-versatile"

    debate_rounds: int = 1
    request_timeout: int = 120

    # Telegram user IDs админов (через запятую). Пусто = любой может менять настройки.
    admin_ids: str = ""


settings = Settings()
