"""Синхронизация объявлений с ads-api.ru."""

from __future__ import annotations

import asyncio
import logging
import os

import aiohttp
from sqlalchemy import select

from database import Property, add_property, async_session_factory


logger = logging.getLogger(__name__)
ADS_API_URL = "https://ads-api.ru/main/api"


def _int_or_none(value: object) -> int | None:
    """Безопасно преобразовать значение в целое число."""
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(" ", "").replace(",", "."))) or None
    except (TypeError, ValueError):
        return None


async def fetch_ads(city: str = "Нальчик", limit: int = 50) -> list[dict]:
    """Получить объявления из ads-api.ru."""
    params = {
        "user": os.getenv("ADS_API_USER", ""),
        "token": os.getenv("ADS_API_TOKEN", ""),
        "city": city,
        "category_id": 2,
        "limit": limit,
        "page": 1,
    }
    proxy = os.getenv("PROXY_URL")
    if proxy:
        logger.info("Используется прокси: %s", proxy.split("@")[-1])

    timeout = aiohttp.ClientTimeout(total=60, connect=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for attempt in range(3):
            try:
                async with session.get(
                    ADS_API_URL,
                    params=params,
                    proxy=proxy,
                    timeout=timeout,
                ) as response:
                    if response.status == 401:
                        logger.error("Неверный логин/токен ads-api.ru")
                        return []
                    if response.status == 403:
                        logger.error("IP заблокирован (проверьте прокси)")
                        return []
                    response.raise_for_status()
                    payload = await response.json(content_type=None)

                if not isinstance(payload, dict) or payload.get("code") != 200:
                    logger.error("API вернул ошибку: %s", payload)
                    return []
                ads = payload.get("data", [])
                if not ads:
                    logger.warning("API вернул пустой список объявлений")
                    return []
                result = [ad for ad in ads if isinstance(ad, dict)]
                logger.info("Получено %d объявлений", len(result))
                return result
            except (asyncio.TimeoutError, aiohttp.ClientError) as error:
                logger.warning("Попытка %d/3 не удалась: %s", attempt + 1, error)
                if attempt == 2:
                    logger.error("Все попытки исчерпаны")
                    return []
                await asyncio.sleep(2)
            except Exception:
                logger.exception("Ошибка получения объявлений ads-api.ru")
                return []
    return []


async def _source_exists(source_url: str) -> bool:
    """Проверить дубликат по URL источника."""
    async with async_session_factory() as session:
        result = await session.execute(select(Property.id).where(Property.source_url == source_url).limit(1))
        return result.scalar_one_or_none() is not None


async def save_ads(ads: list[dict]) -> int:
    """Сохранить новые объявления и вернуть их количество."""
    saved = 0
    for ad in ads:
        try:
            source_url = str(ad.get("url") or "").strip()
            if not source_url or await _source_exists(source_url):
                continue
            params = ad.get("params") or {}
            images = ad.get("images") or []
            first_image = images[0] if images and isinstance(images[0], dict) else {}
            city = str(ad.get("city1") or "").strip()
            property_type = str(ad.get("cat2") or "квартира").strip()
            title = str(ad.get("title") or "Объявление").strip()
            property_id = await add_property(
                title=title,
                price=_int_or_none(ad.get("price")),
                address=ad.get("address", ""),
                district=city or ad.get("region", ""),
                property_type=property_type,
                rooms=_int_or_none(params.get("Количество комнат")),
                area=_int_or_none(params.get("Площадь")),
                floor=_int_or_none(params.get("Этаж")),
                floors_total=_int_or_none(params.get("Этажей в доме")),
                description=ad.get("description", ""),
                photo_url=first_image.get("imgurl"),
                source="ads_api",
                source_url=source_url,
            )
            saved += 1
            logger.info("Сохранено объявление #%s", property_id)
        except Exception:
            logger.exception("Ошибка сохранения объявления ads-api")
    return saved


async def sync_ads(city: str = "Нальчик") -> dict[str, int]:
    """Получить и сохранить объявления выбранного города."""
    ads = await fetch_ads(city=city)
    saved = await save_ads(ads)
    return {"fetched": len(ads), "saved": saved}
