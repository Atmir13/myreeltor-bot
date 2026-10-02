"""Тесты фундамента и создания пользователя."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database import Base, User


@pytest.mark.asyncio
async def test_user_creation() -> None:
    """Пользователь создаётся с выключенным триалом по умолчанию."""
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = User(telegram_id=123456, username="tester")
        session.add(user)
        await session.commit()

        result = await session.execute(select(User).where(User.telegram_id == 123456))
        saved_user = result.scalar_one()

    assert saved_user.username == "tester"
    assert saved_user.trial_used == 0
    assert saved_user.subscribed_to_channel == 0
    await test_engine.dispose()
