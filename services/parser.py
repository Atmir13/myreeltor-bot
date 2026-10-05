"""Разбор естественного языка для поиска недвижимости."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class SearchQuery:
    """Нормализованные параметры поискового запроса."""

    property_type: str | None = None
    rooms: int | None = None
    price_max: int | None = None
    price_min: int | None = None
    district: str | None = None
    area_min: int | None = None
    area_max: int | None = None

    def is_empty(self) -> bool:
        """Вернуть True, если запрос не содержит ни одного параметра."""
        return not any(
            value is not None
            for value in (
                self.property_type,
                self.rooms,
                self.price_max,
                self.price_min,
                self.district,
                self.area_min,
                self.area_max,
            )
        )

    def has_main_filters(self) -> bool:
        """Вернуть True, если задан фильтр типа, комнат, цены или района."""
        return any(
            value is not None
            for value in (
                self.property_type,
                self.rooms,
                self.price_max,
                self.price_min,
                self.district,
            )
        )


_TYPE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("таунхаус", r"\bтаунхаус(?:а|е|ы|ов)?\b"),
    ("квартира", r"\bквартир(?:а|у|ы|е|ой|ам|ами|ах)?\b"),
    ("дом", r"\bдом(?:а|е|ом|у|ов)?\b"),
    ("студия", r"\bстуди(?:я|ю|и|ей|ям|ями|ях)\b"),
)
_ROOM_WORDS = {
    "однушка": 1,
    "однокомнатная": 1,
    "двушка": 2,
    "двухкомнатная": 2,
    "трёшка": 3,
    "трешка": 3,
    "трехкомнатная": 3,
    "трёхкомнатная": 3,
    "четырёшка": 4,
    "четырешка": 4,
    "четырехкомнатная": 4,
    "четырёхкомнатная": 4,
}


def _number(value: str) -> int:
    """Преобразовать число с пробелами в целое."""
    return int(value.replace(" ", "").replace(" ", ""))


def _money(value: str, unit: str | None) -> int:
    """Преобразовать сумму в рубли с учётом млн/тыс."""
    number = float(value.replace(" ", "").replace(" ", "").replace(",", "."))
    normalized_unit = (unit or "").lower()
    if normalized_unit in {"млн", "миллион", "миллиона", "миллионов"}:
        number *= 1_000_000
    elif normalized_unit in {"тыс", "тысяч", "тысячи", "т"}:
        number *= 1_000
    return int(number)


def _parse_rooms(text: str) -> int | None:
    """Найти число комнат в цифровой или разговорной форме."""
    for word, rooms in _ROOM_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", text):
            return rooms

    match = re.search(r"\b([1-9]\d?)\s*(?:-?к|комнат(?:а|ы|у)?|комн)\b", text)
    return int(match.group(1)) if match else None


def _parse_price(text: str) -> tuple[int | None, int | None]:
    """Найти нижнюю и верхнюю границы цены."""
    amount = r"(\d[\d\s]*(?:[.,]\d+)?)\s*(млн|миллион(?:а|ов)?|тыс(?:яч)?|т)?"
    not_area = r"(?!\s*(?:кв\.?\s*м|м²|квадрат(?:ов|ных|а)?))"
    max_match = re.search(
        rf"(?:до|не дороже|максимум)\s*{amount}\s*{not_area}(?:₽|руб(?:лей|ля)?|р\.?)*",
        text,
    )
    min_match = re.search(
        rf"(?:от|не дешевле|минимум)\s*{amount}\s*{not_area}(?:₽|руб(?:лей|ля)?|р\.?)*",
        text,
    )
    price_max = _money(max_match.group(1), max_match.group(2)) if max_match else None
    price_min = _money(min_match.group(1), min_match.group(2)) if min_match else None
    return price_max, price_min


def _parse_district(text: str) -> str | None:
    """Найти название района после слова «район» или перед ним."""
    match = re.search(r"\bрайон\s+([а-яёa-z][а-яёa-z-]{1,39})", text)
    if match:
        return match.group(1).strip().capitalize()
    match = re.search(r"\b([а-яёa-z][а-яёa-z-]{1,39})\s+район\b", text)
    return match.group(1).strip().capitalize() if match else None


def _parse_area(text: str) -> tuple[int | None, int | None]:
    """Найти границы площади в квадратных метрах."""
    value = r"(\d[\d\s]*)"
    units = r"(?:кв\.?\s*м(?:етрах|етра)?|квадрат(?:ных|а|ов)?(?:\s*метр(?:ов|а)?)?|м²)"
    max_match = re.search(rf"до\s*{value}\s*{units}", text)
    min_match = re.search(rf"от\s*{value}\s*{units}", text)
    plain_match = re.search(rf"{value}\s*{units}", text)
    area_max = _number(max_match.group(1)) if max_match else None
    area_min = _number(min_match.group(1)) if min_match else None
    if plain_match and not max_match and not min_match:
        area_min = _number(plain_match.group(1))
    return area_min, area_max


def parse_query(text: str) -> SearchQuery:
    """Преобразовать текст пользователя в фильтры поиска."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    query = SearchQuery()

    for property_type, pattern in _TYPE_PATTERNS:
        if re.search(pattern, normalized):
            query.property_type = property_type
            break
    if query.property_type is None and _parse_rooms(normalized) is not None:
        query.property_type = "квартира"

    query.rooms = _parse_rooms(normalized)
    query.price_max, query.price_min = _parse_price(normalized)
    query.district = _parse_district(normalized)
    query.area_min, query.area_max = _parse_area(normalized)
    return query
