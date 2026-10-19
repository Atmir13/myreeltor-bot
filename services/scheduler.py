"""Планировщик синхронизации объявлений и автопостинга."""

from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from services.ads_api import sync_ads
from services.autoposter import post_random_property


logger = logging.getLogger(__name__)


async def scheduled_sync_ads() -> None:
    """Запустить синхронизацию ads-api вне ночного окна."""
    now = datetime.now()
    if now.hour >= 23 or now.hour < 5:
        logger.info("Ночная пауза, пропуск синхронизации ads")
        return
    logger.info("Запуск синхронизации ads-api.ru")
    try:
        result = await sync_ads()
        logger.info("Синхронизация: получено %d, сохранено %d", result["fetched"], result["saved"])
    except Exception:
        logger.exception("Ошибка синхронизации ads")


async def scheduled_autopost(bot: Bot) -> None:
    """Запустить автопостинг вне ночного окна."""
    now = datetime.now()
    if now.hour >= 23 or now.hour < 5:
        logger.info("Ночная пауза, пропуск автопостера")
        return
    logger.info("Запуск автопостера в канал")
    try:
        await post_random_property(bot)
    except Exception:
        logger.exception("Ошибка автопостера")


def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Создать и запустить планировщик задач."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(scheduled_sync_ads, trigger="cron", hour="5-23/3", minute=0,
                      id="ads_api_sync", replace_existing=True)
    scheduler.add_job(scheduled_autopost, trigger="cron", hour="5-23/3", minute=30,
                      args=[bot], id="autoposter", replace_existing=True)
    scheduler.start()
    logger.info("Планировщик запущен: ads_api + автопостер каждые 3 часа")
    return scheduler
