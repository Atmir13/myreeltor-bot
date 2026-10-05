"""Тесты regex-парсера поисковых запросов."""

from services.parser import parse_query


def test_two_room_apartment_and_max_price() -> None:
    query = parse_query("двушка до 15 млн")
    assert query.property_type == "квартира"
    assert query.rooms == 2
    assert query.price_max == 15_000_000


def test_house_four_rooms_twenty_million() -> None:
    query = parse_query("дом 4 комнаты до 20 млн")
    assert query.property_type == "дом"
    assert query.rooms == 4
    assert query.price_max == 20_000_000


def test_studio_district() -> None:
    query = parse_query("студия район Центральный")
    assert query.property_type == "студия"
    assert query.district == "Центральный"


def test_district_before_word() -> None:
    assert parse_query("квартира Центральный район").district == "Центральный"


def test_min_price() -> None:
    assert parse_query("дом от 5 млн").price_min == 5_000_000


def test_plain_numeric_price() -> None:
    assert parse_query("квартира до 15000000").price_max == 15_000_000


def test_area_max() -> None:
    assert parse_query("квартира до 70 кв м").area_max == 70


def test_area_min() -> None:
    assert parse_query("дом от 40 квадратов").area_min == 40


def test_numeric_rooms() -> None:
    assert parse_query("квартира 2к").rooms == 2


def test_three_room_word() -> None:
    assert parse_query("трёшка").rooms == 3


def test_townhouse() -> None:
    assert parse_query("таунхаус до 12 млн").property_type == "таунхаус"


def test_empty_query() -> None:
    query = parse_query("хочу что-нибудь хорошее")
    assert query.is_empty()
    assert not query.has_main_filters()
