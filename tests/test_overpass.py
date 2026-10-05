"""Тесты обработки ответа Overpass API."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.overpass import find_nearby_infrastructure


class FakeResponse:
    """Минимальный асинхронный ответ aiohttp для теста."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def json(self) -> dict:
        return self.payload


class FakeSession:
    """Минимальная асинхронная сессия aiohttp для теста."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def post(self, *args: object, **kwargs: object) -> FakeResponse:
        return FakeResponse(self.payload)


@pytest.mark.asyncio
async def test_overpass_response_is_normalized_and_sorted() -> None:
    payload = {
        "elements": [
            {
                "type": "node",
                "lat": 55.7522,
                "lon": 37.6156,
                "tags": {"amenity": "school", "name": "Школа дальняя"},
            },
            {
                "type": "way",
                "center": {"lat": 55.7558, "lon": 37.6173},
                "tags": {"amenity": "kindergarten", "name": "Солнышко"},
            },
            {
                "type": "node",
                "lat": 55.7557,
                "lon": 37.6172,
                "tags": {"amenity": "school", "name": "Школа ближняя"},
            },
            {
                "type": "node",
                "lat": 55.7557,
                "lon": 37.6172,
                "tags": {"amenity": "school"},
            },
        ]
    }
    with patch(
        "services.overpass.aiohttp.ClientSession",
        return_value=FakeSession(payload),
    ):
        result = await find_nearby_infrastructure(55.7558, 37.6173)

    assert [item["name"] for item in result["schools"]] == [
        "Школа ближняя",
        "Школа дальняя",
    ]
    assert result["kindergartens"][0]["name"] == "Солнышко"
    assert result["schools"][0]["distance_m"] <= result["schools"][1]["distance_m"]
    assert "lat" in result["schools"][0]
    assert "lon" in result["schools"][0]
