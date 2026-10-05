"""Regex-парсер запросов на поиск недвижимости."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SearchQuery:
    """Разобранный поисковый запрос."""

    property_type: str | None = None
    rooms: int | None = None
    price_max: int | None = None
    price_min: int | None = None
    district: str | None = None
    area_min: int | None = None
    area_max: int | None = None

    def is_empty(self) -> bool:
        """Все ли поля пустые."""
        return all(
            v is None
            for v in (
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
        """Есть ли хотя бы один ключевой фильтр (тип, комнаты, цена)."""
        return any(
            v is not None
            for v in (self.property_type, self.rooms, self.price_max)
        )


# ============================
# Регулярные выражения
# ============================

# Типы недвижимости
RE_TYPE_HOUSE = re.compile(r"\b(дом|дома|домик|коттедж|таунхаус)\b", re.IGNORECASE)
RE_TYPE_APARTMENT = re.compile(r"\b(квартира|квартиру|квартиры|кв)\b", re.IGNORECASE)
RE_TYPE_STUDIO = re.compile(r"\b(студия|студию|студии)\b", re.IGNORECASE)

# Комнаты — числом
RE_ROOMS_NUM = re.compile(r"\b(\d+)\s*(?:-?\s*комнат|к\b|комн)", re.IGNORECASE)

# Комнаты — словами
RE_ROOMS_WORD = re.compile(
    r"\b(однушка|однокомнатная|двушка|двухкомнатная|трёшка|трешка|трехкомнатная|"
    r"четырёшка|четырехкомнатная)\b",
    re.IGNORECASE,
)

# Цена — «до 15 млн», «до 15 миллионов»
RE_PRICE_MILLIONS = re.compile(
    r"до\s+(\d+[.,]?\d*)\s*(?:млн|миллион|миллионов|млр)",
    re.IGNORECASE,
)

# Цена — «до 8000000», «до 8 000 000»
RE_PRICE_NUMBER = re.compile(r"до\s+(\d[\d\s]{4,})\s*(?:₽|руб|р\b)?", re.IGNORECASE)

# Цена — «от 5 млн», «от 5000000»
RE_PRICE_FROM = re.compile(
    r"от\s+(\d+[.,]?\d*)\s*(млн|миллион|миллионов)",
    re.IGNORECASE,
)

# Район — «район Центральный», «в Центральном районе», «Центральный район»
RE_DISTRICT = re.compile(
    r"(?:район[е]?\s+|в\s+)([А-ЯЁ][а-яё\-]+(?:ский|ской|ий|ый|ой|овский))",
    re.IGNORECASE,
)
RE_DISTRICT_SIMPLE = re.compile(
    r"([А-ЯЁ][а-яё\-]+)\s+район",
    re.IGNORECASE,
)

# Площадь — «от 50 кв м», «50 квадратов», «50 м²»
RE_AREA = re.compile(
    r"(\d+)\s*(?:кв\.?\s*м|квадратов|квадрат|м²|м2)",
    re.IGNORECASE,
)
RE_AREA_MIN = re.compile(r"от\s+(\d+)\s*(?:кв\.?\s*м|квадратов|м²|м2)", re.IGNORECASE)


# ============================
# Разбор
# ============================

def _parse_rooms(text: str) -> int | None:
    """Извлечь количество комнат."""
    # Словами
    word_match = RE_ROOMS_WORD.search(text)
    if word_match:
        word = word_match.group(1).lower()
        if word in ("однушка", "однокомнатная"):
            return 1
        if word in ("двушка", "двухкомнатная"):
            return 2
        if word in ("трёшка", "трешка", "трехкомнатная"):
            return 3
        if word in ("четырёшка", "четырехкомнатная"):
            return 4

    # Числом
    num_match = RE_ROOMS_NUM.search(text)
    if num_match:
        return int(num_match.group(1))

    return None


def _parse_price(text: str) -> tuple[int | None, int | None]:
    """Извлечь цену: (price_max, price_min)."""
    price_max: int | None = None
    price_min: int | None = None

    # «до 15 млн»
    millions = RE_PRICE_MILLIONS.search(text)
    if millions:
        value = float(millions.group(1).replace(",", "."))
        price_max = int(value * 1_000_000)

    # «до 8000000»
    if price_max is None:
        number = RE_PRICE_NUMBER.search(text)
        if number:
            digits = re.sub(r"\s", "", number.group(1))
            price_max = int(digits)

    # «от 5 млн»
    from_match = RE_PRICE_FROM.search(text)
    if from_match:
        value = float(from_match.group(1).replace(",", "."))
        price_min = int(value * 1_000_000)

    return price_max, price_min


def _parse_type(text: str) -> str | None:
    """Извлечь тип недвижимости."""
    if RE_TYPE_STUDIO.search(text):
        return "студия"
    if RE_TYPE_HOUSE.search(text):
        return "дом"
    if RE_TYPE_APARTMENT.search(text):
        return "квартира"
    return None


def _parse_district(text: str) -> str | None:
    """Извлечь район."""
    match = RE_DISTRICT_SIMPLE.search(text)
    if match:
        return match.group(1).strip()

    match = RE_DISTRICT.search(text)
    if match:
        return match.group(1).strip()

    return None


def _parse_area(text: str) -> tuple[int | None, int | None]:
    """Извлечь площадь: (area_min, area_max)."""
    area_min: int | None = None
    area_max: int | None = None

    min_match = RE_AREA_MIN.search(text)
    if min_match:
        area_min = int(min_match.group(1))
    else:
        # «50 кв м» — считаем как минимум
        match = RE_AREA.search(text)
        if match:
            area_min = int(match.group(1))

    return area_min, area_max


def parse_query(text: str) -> SearchQuery:
    """Разобрать текст запроса в SearchQuery."""
    if not text:
        return SearchQuery()

    # Убираем лишние символы
    text = text.strip()

    price_max, price_min = _parse_price(text)
    area_min, area_max = _parse_area(text)

    return SearchQuery(
        property_type=_parse_type(text),
        rooms=_parse_rooms(text),
        price_max=price_max,
        price_min=price_min,
        district=_parse_district(text),
        area_min=area_min,
        area_max=area_max,
    )
