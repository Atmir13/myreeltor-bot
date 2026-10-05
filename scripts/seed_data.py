"""Заполнить локальную базу семью демонстрационными объектами."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

# Добавляем корень проекта в sys.path для запуска из каталога scripts.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import add_property, init_db, mark_property_sold  # noqa: E402


OBJECTS = [
    {
        "title": "Двухкомнатная на Ленина",
        "price": 8_200_000,
        "rooms": 2,
        "area": 54,
        "address": "ул. Ленина, 15",
        "district": "Центральный",
        "property_type": "квартира",
        "seller_telegram": "reeltor_ivan",
    },
    {
        "title": "Трёхкомнатная в новостройке",
        "price": 12_500_000,
        "rooms": 3,
        "area": 78,
        "address": "ул. Мира, 42",
        "district": "Центральный",
        "property_type": "квартира",
        "source_url": "https://www.avito.ru/test",
    },
    {
        "title": "Студия у метро",
        "price": 4_800_000,
        "rooms": 1,
        "area": 28,
        "address": "ул. Садовая, 8",
        "district": "Северный",
        "property_type": "студия",
        "seller_telegram": "studio_seller",
    },
    {
        "title": "Частный дом с участком",
        "price": 18_000_000,
        "rooms": 4,
        "area": 150,
        "address": "ул. Лесная, 3",
        "district": "Загородный",
        "property_type": "дом",
        "seller_telegram": "dom_seller",
    },
    {
        "title": "Однокомнатная на Южной",
        "price": 5_500_000,
        "rooms": 1,
        "area": 38,
        "address": "ул. Южная, 22",
        "district": "Южный",
        "property_type": "квартира",
        "source_url": "https://www.cian.ru/test",
    },
    {
        "title": "Двухкомнатная на Западной",
        "price": 9_800_000,
        "rooms": 2,
        "area": 62,
        "address": "ул. Западная, 11",
        "district": "Западный",
        "property_type": "квартира",
        "seller_telegram": "reeltor_anna",
    },
    {
        "title": "Студия в центре",
        "price": 6_000_000,
        "rooms": 1,
        "area": 32,
        "address": "ул. Главная, 1",
        "district": "Центральный",
        "property_type": "студия",
    },
]


async def main() -> None:
    """Создать таблицы, добавить объекты и продать объект номер семь."""
    await init_db()
    property_ids: list[int] = []
    for item in OBJECTS:
        property_id = await add_property(**item)
        property_ids.append(property_id)
        print(f"Добавлен объект {property_id}: {item['title']}")

    await mark_property_sold(property_ids[-1])
    print(f"Объект {property_ids[-1]} помечен как проданный")


if __name__ == "__main__":
    asyncio.run(main())
