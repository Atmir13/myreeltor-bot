"""Общие модели и асинхронное подключение к базе данных."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс ORM-моделей."""


class User(Base):
    """Пользователь Telegram."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trial_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    subscribed_to_channel: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="user")


class Property(Base):
    """Объект недвижимости."""

    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    area: Mapped[int | None] = mapped_column(Integer, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    nearby_infrastructure: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Subscription(Base):
    """Платная подписка пользователя."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    subscription_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship(back_populates="subscriptions")


class Advertiser(Base):
    """Заявка рекламодателя."""

    __tablename__ = "advertisers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ChatAgreement(Base):
    """Согласие участника чата с правилами."""

    __tablename__ = "chat_agreements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    agreed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def build_engine(database_url: str) -> AsyncEngine:
    """Создать engine с таймаутом подключения к SQLite пять секунд."""
    connect_args: dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        connect_args["timeout"] = 5
    return create_async_engine(database_url, echo=False, connect_args=connect_args)


def default_database_url() -> str:
    """Вернуть путь к локальной базе проекта."""
    database_path = Path(__file__).resolve().parent / "data" / "realestate.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{database_path.as_posix()}"


engine = build_engine(default_database_url())
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Создать таблицы, если они ещё не существуют."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
