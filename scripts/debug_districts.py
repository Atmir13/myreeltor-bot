"""Диагностика значений районов и поиска по базе MyReeltor."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта для запуска скрипта напрямую.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from database import Property, async_session_factory, search_properties  # noqa: E402


async def main() -> None:
    """Вывести данные районов и результаты тестовых запросов."""
    async with async_session_factory() as session:
        districts = await session.execute(
            select(Property.district).where(Property.district.is_not(None)).distinct().order_by(Property.district)
        )
        print("Уникальные district:")
        for value in districts.scalars():
            print(f"  {value!r}")

        nalchik = await session.execute(
            select(Property).where(Property.address.ilike("%Нальчик%")).limit(5)
        )
        other = await session.execute(
            select(Property).where(
                Property.address.is_not(None),
                ~Property.address.ilike("%Нальчик%"),
            ).limit(5)
        )
        print("\nПримеры адресов Нальчика:")
        for prop in nalchik.scalars():
            print(f"  {prop.id}: {prop.address!r} (district={prop.district!r})")
        print("\nПримеры адресов других городов:")
        for prop in other.scalars():
            print(f"  {prop.id}: {prop.address!r} (district={prop.district!r})")

    print("\nРезультаты поиска:")
    for value in ("Нальчик", "г.о. Нальчик", "г. Нальчик", "Майский", "Терек", "Прохладный"):
        properties = await search_properties(district=value, limit=5)
        print(f"  {value!r}: {len(properties)}")


if __name__ == "__main__":
    asyncio.run(main())
