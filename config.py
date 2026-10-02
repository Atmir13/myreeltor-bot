"""Конфигурация приложения."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")


class ConfigurationError(ValueError):
    """Ошибка обязательной конфигурации."""


@dataclass(frozen=True)
class Settings:
    """Настройки бота и базы данных."""

    bot_token: str
    channel_id: str
    admin_id: int
    database_url: str


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value == "change_me":
        raise ConfigurationError(f"Не задана обязательная переменная {name}")
    return value


def load_settings() -> Settings:
    """Загрузить и проверить настройки из .env."""
    try:
        admin_id = int(_required("ADMIN_ID"))
    except ValueError as error:
        raise ConfigurationError("ADMIN_ID должен быть целым числом") from error

    return Settings(
        bot_token=_required("BOT_TOKEN"),
        channel_id=_required("CHANNEL_ID"),
        admin_id=admin_id,
        database_url=_required("DATABASE_URL"),
    )


settings = load_settings()
