"""Заполнить локальную базу демонстрационными объектами."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import add_property, init_db, mark_property_sold  # noqa: E402


OBJECTS = [
    {
        "title": "Светлая двушка у парка",
        "price": 12_500_000,
        "rooms": 2,
        "area": 58,
        "address": "ул. Лесная, 12",
        "district": "Центральный",
        "property_type": "квартира",
        "description": "Ремонт, большая кухня и окна во двор.",
        "source_url": "https://example.com/listing/1",
    },
    {
        "title": "Трёшка для семьи",
        "price": 18_900_000,
        "rooms": 3,
        "area": 82,
        "address": "пр-т Мира, 8",
        "district": "Центральный",
        "property_type": "квартира",
        "description": "Три изолированные комнаты, рядом школа.",
        "seller_telegram": "myreeltor_demo",
    },
    {
        "title": "Загородный дом с участком",
        "price": 19_500_000,
        "rooms": 4,
        "area": 145,
        "address": "д. Новая, 4",
        "district": "Пригородный",
        "property_type": "дом",
        "description": "Двухэтажный дом, участок 8 соток.",
        "source_url": "https://example.com/listing/3",
    },
    {
        "title": "Компактная студия",
        "price": 7_800_000,
        "rooms": 1,
        "area": 31,
        "address": "ул. Речная, 5",
        "district": "Северный",
        "property_type": "студия",
        "description": "Новый дом, закрытый двор.",
        "seller_telegram": "myreeltor_demo",
    },
    {
        "title": "Таунхаус с гаражом",
        "price": 15_000_000,
        "rooms": 3,
        "area": 110,
        "address": "кп Сосновый, 21",
        "district": "Пригородный",
        "property_type": "таунхаус",
        "description": "Тихий посёлок и готовая отделка.",
        "source_url": "https://example.com/listing/5",
    },
    {
        "title": "Проданная квартира у метро",
        "price": 10_000_000,
        "rooms": 2,
        "area": 52,
        "address": "ул. Центральная, 1",
        "district": "Центральный",
        "property_type": "квартира",
        "description": "Демонстрационный объект со статусом sold.",
        "source_url": "https://example.com/listing/6",
    },
]


async def main() -> None:
    """Создать таблицы и добавить демонстрационные записи."""
    await init_db()
    for index, item in enumerate(OBJECTS):
        property_id = await add_property(**item)
        if index == len(OBJECTS) - 1:
            await mark_property_sold(property_id)
        print(f"Добавлен объект {property_id}: {item['title']}")


if __name__ == "__main__":
    asyncio.run(main())
