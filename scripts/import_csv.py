"""Импорт объявлений из CSV-файла ads-api.ru в базу бота."""

from __future__ import annotations

import asyncio
import csv
import logging
import sys
from pathlib import Path
from typing import Any

# Добавляем корень проекта в sys.path для запуска файла напрямую.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from database import (  # noqa: E402
    Property,
    add_property,
    async_session_factory,
    init_db,
    update_property_coords,
)


logger = logging.getLogger(__name__)


def parse_dop_params(s: str) -> dict[str, str]:
    """Разобрать строку дополнительных параметров объявления."""
    result: dict[str, str] = {}
    for item in (s or "").split("|"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        if key:
            result[key] = value.strip()
    return result


def parse_first_photo(photos_str: str) -> str | None:
    """Вернуть первую ссылку на фотографию или None."""
    for photo in (photos_str or "").split(","):
        photo = photo.strip()
        if photo:
            return photo
    return None


def normalize_property_type(category2: str) -> str:
    """Привести категорию объявления к типу объекта бота."""
    value = (category2 or "").strip()
    mapping = {
        "Квартиры": "квартира",
        "Дома, дачи, коттеджи": "дом",
        "Земельные участки": "участок",
        "Коммерческая недвижимость": "коммерция",
    }
    return mapping.get(value, value)


def _text(row: dict[str, str], name: str) -> str:
    """Получить очищенное текстовое значение CSV."""
    return (row.get(name) or "").strip()


def _number(value: str, kind: type[int] | type[float]) -> int | float | None:
    """Безопасно преобразовать число с пробелами и русской запятой."""
    value = (value or "").strip().replace(" ", "").replace("\u00a0", "")
    if not value:
        return None
    try:
        return kind(value.replace(",", ".") if kind is float else value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: str) -> int | None:
    """Преобразовать значение в целое число."""
    number = _number(value, int)
    return number if isinstance(number, int) else None


def _parse_float(value: str) -> float | None:
    """Преобразовать значение в число с плавающей точкой."""
    number = _number(value, float)
    return number if isinstance(number, float) else None


async def _source_url_exists(source_url: str) -> bool:
    """Проверить наличие объявления с таким URL."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Property.id).where(Property.source_url == source_url).limit(1)
        )
        return result.scalar_one_or_none() is not None


async def import_csv(file_path: str) -> dict[str, int]:
    """Импортировать объявления из CSV и вернуть статистику."""
    statistics = {"total": 0, "imported": 0, "skipped": 0}
    await init_db()

    with open(file_path, "r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=";")
        for row_number, raw_row in enumerate(reader, start=2):
            statistics["total"] += 1
            row: dict[str, str] = {
                str(key).strip(): (value or "")
                for key, value in raw_row.items()
                if key is not None
            }
            source_url = _text(row, "URL")
            if not source_url:
                statistics["skipped"] += 1
                logger.warning("Строка %s пропущена: отсутствует URL", row_number)
                continue

            try:
                if await _source_url_exists(source_url):
                    statistics["skipped"] += 1
                    logger.info("Строка %s пропущена: URL уже есть в базе", row_number)
                    continue

                params = parse_dop_params(_text(row, "Доп.параметры"))
                price = _parse_int(_text(row, "Цена"))
                rooms = _parse_int(params.get("Количество комнат", ""))
                area = _parse_float(params.get("Площадь", ""))
                floor = _parse_int(params.get("Этаж", ""))
                floors_total = _parse_int(params.get("Этажей в доме", ""))
                latitude = _parse_float(_text(row, "lat"))
                longitude = _parse_float(_text(row, "lng"))

                property_id = await add_property(
                    title=_text(row, "Название"),
                    price=price,
                    address=_text(row, "Адрес") or _text(row, "Метро/Район"),
                    district=_text(row, "Метро/Район"),
                    property_type=normalize_property_type(_text(row, "Категория2")),
                    rooms=rooms,
                    area=int(area) if area is not None else None,
                    floor=floor,
                    floors_total=floors_total,
                    description=_text(row, "Описание"),
                    photo_url=parse_first_photo(_text(row, "Ссылки на картинки")),
                    source="ads_api",
                    source_url=source_url,
                )
                if latitude is not None and longitude is not None:
                    await update_property_coords(property_id, latitude, longitude)

                statistics["imported"] += 1
                print(f"Импортировано объявление {property_id}: {_text(row, 'Название')}")
            except Exception:
                statistics["skipped"] += 1
                logger.exception("Ошибка в строке %s: объявление пропущено", row_number)

    print(
        "Импорт завершён: "
        f"всего {statistics['total']}, "
        f"импортировано {statistics['imported']}, "
        f"пропущено {statistics['skipped']}"
    )
    return statistics


async def main() -> None:
    """Запустить импорт из аргумента командной строки."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if len(sys.argv) != 2:
        print("Использование: python scripts/import_csv.py путь/к/файлу.csv")
        raise SystemExit(2)
    await import_csv(sys.argv[1])


if __name__ == "__main__":
    asyncio.run(main())
