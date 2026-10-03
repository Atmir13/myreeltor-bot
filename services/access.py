
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from config import settings
from database import User, has_active_subscription, update_channel_subscription


logger = logging.getLogger(__name__)


# Уровни доступа
LEVEL_TRIAL = "trial"       # триал: 2 объекта, один раз
LEVEL_CHANNEL = "channel"   # подписан на канал: 5 объектов, один раз
LEVEL_PAID = "paid"         # платная подписка: безлимит
LEVEL_BLOCKED = "blocked"   # триал сгорел, подписки нет


# Сколько объектов показывать на каждом уровне
LIMITS = {
    LEVEL_TRIAL: 2,
    LEVEL_CHANNEL: 5,
    LEVEL_PAID: None,  # None = без ограничений
    LEVEL_BLOCKED: 0,
}


def get_limit_for_level(level: str) -> int | None:
    """Вернуть лимит объектов для уровня доступа."""
    return LIMITS.get(level, 0)


async def check_channel_subscription(bot: Bot, user_id: int) -> bool:
    """Проверить, подписан ли пользователь на канал из настроек."""
    if not settings.channel_id:
        logger.warning("CHANNEL_ID не задан — проверка подписки пропущена")
        return False
    try:
        member = await bot.get_chat_member(settings.channel_id, user_id)
        return member.status in ("member", "administrator", "creator")
    except TelegramBadRequest as exc:
        logger.warning("Не удалось проверить подписку: %s", exc)
        return False
    except Exception:
        logger.exception("Ошибка при проверке подписки на канал")
        return False


async def get_access_level(bot: Bot, user: User) -> str:
    """Определить уровень доступа пользователя."""
    # 1. Платная подписка — высший приоритет
    if has_active_subscription(user):
        return LEVEL_PAID

    # 2. Триал ещё не использован
    if user.trial_used == 0:
        # Проверяем подписку на канал
        is_subscribed = await check_channel_subscription(bot, user.telegram_id)
        # Обновляем кэш в базе
        await update_channel_subscription(user.telegram_id, 1 if is_subscribed else 0)
        if is_subscribed:
            return LEVEL_CHANNEL
        return LEVEL_TRIAL

    # 3. Триал сгорел, платной подписки нет
    return LEVEL_BLOCKED