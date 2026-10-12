"""Надёжный импорт объявлений ads-api.ru в базу MyReeltor."""

from __future__ import annotations

import asyncio
import csv
import logging
import sys
from pathlib import Path

# Добавляем корень проекта для запуска скрипта напрямую.
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


def parse_dop_params(value: str | None) -> dict[str, str]:
    """Разобрать строку параметров формата «ключ=значение|ключ=значение»."""
    result: dict[str, str] = {}
    for item in (value or "").split("|"):
        if "=" not in item:
            continue
        key, item_value = item.split("=", 1)
        key = key.strip()
        if key:
            result[key] = item_value.strip()
    return result


def parse_first_photo(value: str | None) -> str | None:
    """Вернуть первую непустую ссылку на фотографию."""
    for photo in (value or "").split(","):
        if photo.strip():
            return photo.strip()
    return None


def normalize_property_type(category: str | None) -> str | None:
    """Нормализовать категорию недвижимости для каталога."""
    value = (category or "").strip()
    return {
        "Квартиры": "квартира",
        "Дома, дачи, коттеджи": "дом",
        "Земельные участки": "участок",
        "Коммерческая недвижимость": "коммерция",
    }.get(value, value or None)


def text(row: dict[str, str], column: str) -> str:
    """Получить очищенное значение колонки."""
    value = row.get(column, "")
    return str(value or "").strip()


def parse_int(value: str | None) -> int | None:
    """Преобразовать целое число, поддерживая пробелы и русские разделители."""
    raw = (value or "").strip().replace(" ", "").replace("\u00a0", "")
    if not raw:
        return None
    try:
        return int(float(raw.replace(",", ".")))
    except (TypeError, ValueError):
        return None


def parse_float(value: str | None) -> float | None:
    """Преобразовать число с плавающей точкой."""
    raw = (value or "").strip().replace(" ", "").replace("\u00a0", "")
    if not raw:
        return None
    try:
        return float(raw.replace(",", "."))
    except (TypeError, ValueError):
        return None


def make_address(city: str, street: str) -> str | None:
    """Сформировать адрес с городом в начале."""
    if city and street:
        return f"г. {city}, {street}"
    if city:
        return f"г. {city}"
    return street or None


async def existing_urls() -> set[str]:
    """Получить URL уже имеющихся объявлений для защиты от дублей."""
    async with async_session_factory() as session:
        result = await session.execute(select(Property.source_url).where(Property.source_url.is_not(None)))
        return {url for url in result.scalars() if url}


async def import_csv(file_path: str) -> dict[str, int]:
    """Импортировать все корректные строки CSV и вернуть статистику."""
    statistics = {"total": 0, "imported": 0, "skipped": 0}
    await init_db()

    with open(file_path, "r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=";")
        rows = list(reader)
    statistics["total"] = len(rows)
    print(f"Всего строк в CSV: {statistics['total']}")

    known_urls = await existing_urls()
    for row_number, raw_row in enumerate(rows, start=2):
        try:
            if not isinstance(raw_row, dict) or None in raw_row:
                raise ValueError("повреждённая структура строки CSV")
            row = {str(key).strip(): str(value or "") for key, value in raw_row.items() if key is not None}
            source_url = text(row, "URL")
            if not source_url:
                raise ValueError("отсутствует URL")
            if source_url in known_urls:
                raise ValueError("URL уже есть в базе")

            title = text(row, "Название")
            if not title:
                raise ValueError("отсутствует название")
            city = text(row, "Город")
            street = text(row, "Адрес")
            params = parse_dop_params(text(row, "Доп.параметры"))
            property_id = await add_property(
                title=title,
                price=parse_int(text(row, "Цена")),
                address=make_address(city, street),
                district=city or None,
                property_type=normalize_property_type(text(row, "Категория2")),
                rooms=parse_int(params.get("Количество комнат")),
                area=parse_int(params.get("Площадь")),
                floor=parse_int(params.get("Этаж")),
                floors_total=parse_int(params.get("Этажей в доме")),
                description=text(row, "Описание") or None,
                photo_url=parse_first_photo(text(row, "Ссылки на картинки")),
                source="ads_api",
                source_url=source_url,
            )
            latitude = parse_float(text(row, "lat"))
            longitude = parse_float(text(row, "lng"))
            if latitude is not None and longitude is not None:
                await update_property_coords(property_id, latitude, longitude)
            known_urls.add(source_url)
            statistics["imported"] += 1
        except Exception as error:
            statistics["skipped"] += 1
            reason = str(error) or error.__class__.__name__
            print(f"  Строка {row_number}: пропущена — {reason}")
            logger.exception("Ошибка импорта строки %s", row_number)

    print(f"Импортировано: {statistics['imported']}, пропущено: {statistics['skipped']}")
    return statistics


async def main() -> None:
    """Запустить импорт из аргумента командной строки."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if len(sys.argv) != 2:
        print("Использование: python scripts/import_csv.py путь/к/файлу.csv")
        raise SystemExit(2)
    await import_csv(sys.argv[1])


if __name__ == "__main__":
    asyncio.run(main())
