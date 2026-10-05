"""Тесты ссылок OpenStreetMap."""

from types import SimpleNamespace

import pytest

from services.map_generator import generate_map_links, generate_osm_link


@pytest.mark.asyncio
async def test_generate_osm_link() -> None:
    link = await generate_osm_link(55.7558, 37.6173)
    assert link == (
        "https://www.openstreetmap.org/?mlat=55.7558&mlon=37.6173"
        "#map=16/55.7558/37.6173"
    )


@pytest.mark.asyncio
async def test_generate_map_links_without_coordinates() -> None:
    result = await generate_map_links(SimpleNamespace(latitude=None, longitude=None))
    assert result == {"osm": None}


@pytest.mark.asyncio
async def test_generate_map_links_with_coordinates() -> None:
    result = await generate_map_links(SimpleNamespace(latitude=55.75, longitude=37.61))
    assert result["osm"] is not None
    assert "openstreetmap.org" in result["osm"]
