"""Конфигурация. Секреты из .env, провайдеры из providers.json, инфраструктура из settings.json."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).parent
PROVIDERS_JSON = ROOT / "providers.json"
SETTINGS_JSON = ROOT / "settings.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str = ""

    # Роли → "provider_name/model_name" (заполняются configure.py)
    classifier_model: str = ""
    orchestrator_model: str = ""
    coder_a_model: str = ""
    coder_b_model: str = ""
    critic_model: str = ""
    judge_model: str = ""

    debate_rounds: int = 1
    request_timeout: int = 120
    admin_ids: str = ""


settings = Settings()


def load_providers_config() -> list[dict]:
    """Загружает провайдеров из providers.json.
    Каждый элемент: {"name": ..., "base_url": ..., "api_key": ..., "enabled_models": [...]}
    """
    if not PROVIDERS_JSON.exists():
        return []
    try:
        data = json.loads(PROVIDERS_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def load_infra_settings() -> dict:
    """Загружает настройки инфраструктуры из settings.json."""
    defaults = {
        "debate_rounds": 1,
        "request_timeout": 120,
        "temperature": {
            "classifier": 0.0, "orchestrator": 0.4,
            "coder_a": 0.3, "coder_b": 0.3,
            "critic": 0.5, "judge": 0.2,
        },
        "max_tokens": {
            "classifier": 10, "orchestrator": 2048,
            "coder_a": 4096, "coder_b": 4096,
            "critic": 2048, "judge": 4096,
        },
        "judge_mode": "merge_or_pick",
        "response_language": "ru",
        "streaming_enabled": True,
        "parallel_coders": True,
        "show_thinking_in_tg": False,
        "max_input_length": 10000,
        "anti_fluff_enabled": True,
        "custom_prompts": {},
    }
    if not SETTINGS_JSON.exists():
        return defaults
    try:
        data = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        for k, v in defaults.items():
            if k not in data:
                data[k] = v
            elif isinstance(v, dict) and isinstance(data[k], dict):
                data[k] = {**v, **data[k]}
        return data
    except (json.JSONDecodeError, OSError):
        return defaults
