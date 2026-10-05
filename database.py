
"""Общие модели и асинхронное подключение к базе данных."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func, or_, select
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
    subscription_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="user")


class Property(Base):
    """Объект недвижимости."""

    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Основные поля
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Локация
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    district: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Параметры
    property_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    rooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    area: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floors_total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Медиа
    photo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    nearby_infrastructure: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Источник
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    seller_telegram: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Статус
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False, index=True)
    sold_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Служебные
    last_posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Subscription(Base):
    """История платежей и подписок."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    subscription_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_stars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

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
    """Вернуть URL базы: из переменной окружения или локальный путь."""
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url
    database_path = Path(__file__).resolve().parent / "data" / "realestate.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{database_path.as_posix()}"


engine = build_engine(default_database_url())
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Создать таблицы, если они ещё не существуют."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


# ============================
# Функции для работы с юзером
# ============================

async def get_user(telegram_id: int) -> User | None:
    """Вернуть пользователя по telegram_id или None."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def get_or_create_user(telegram_id: int, username: str | None = None) -> User:
    """Вернуть пользователя, создав его при первом обращении."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(telegram_id=telegram_id, username=username)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user


async def update_trial_used(telegram_id: int) -> None:
    """Пометить, что бесплатный запрос использован."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is not None:
            user.trial_used = 1
            await session.commit()


async def update_channel_subscription(telegram_id: int, status: int) -> None:
    """Обновить кэш подписки на канал (0 или 1)."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is not None:
            user.subscribed_to_channel = status
            await session.commit()


async def update_subscription(
    telegram_id: int,
    days: int = 30,
    payment_id: str | None = None,
    amount_stars: int | None = None,
) -> datetime:
    """Продлить платную подписку и записать платёж в историю."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise ValueError("Пользователь не найден")

        now = datetime.utcnow()
        base = (
            user.subscription_expires_at
            if user.subscription_expires_at and user.subscription_expires_at > now
            else now
        )
        expires_at = base + timedelta(days=days)
        user.subscription_expires_at = expires_at

        subscription = Subscription(
            user_id=user.id,
            subscription_expires_at=expires_at,
            payment_id=payment_id,
            amount_stars=amount_stars,
        )
        session.add(subscription)
        await session.commit()
        return expires_at


def has_active_subscription(user: User) -> bool:
    """Проверить, активна ли платная подписка."""
    if user.subscription_expires_at is None:
        return False
    return user.subscription_expires_at > datetime.utcnow()


# ============================
# Функции для работы с объектами
# ============================

async def add_property(
    title: str,
    price: int | None = None,
    address: str | None = None,
    district: str | None = None,
    property_type: str | None = None,
    rooms: int | None = None,
    area: int | None = None,
    floor: int | None = None,
    floors_total: int | None = None,
    description: str | None = None,
    photo_url: str | None = None,
    source: str | None = "manual",
    source_url: str | None = None,
    seller_telegram: str | None = None,
) -> int:
    """Добавить объект и вернуть его ID."""
    async with async_session_factory() as session:
        prop = Property(
            title=title,
            price=price,
            address=address,
            district=district,
            property_type=property_type,
            rooms=rooms,
            area=area,
            floor=floor,
            floors_total=floors_total,
            description=description,
            photo_url=photo_url,
            source=source,
            source_url=source_url,
            seller_telegram=seller_telegram,
            status="active",
        )
        session.add(prop)
        await session.commit()
        await session.refresh(prop)
        return prop.id


async def update_property_coords(prop_id: int, lat: float, lon: float) -> bool:
    """Сохранить координаты объекта."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Property).where(Property.id == prop_id)
        )
        prop = result.scalar_one_or_none()
        if prop is None:
            return False
        prop.latitude = lat
        prop.longitude = lon
        await session.commit()
        return True


async def get_property_by_id(prop_id: int) -> Property | None:
    """Вернуть объект по ID."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Property).where(Property.id == prop_id)
        )
        return result.scalar_one_or_none()


async def mark_property_sold(prop_id: int) -> bool:
    """Пометить объект как проданный."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Property).where(Property.id == prop_id)
        )
        prop = result.scalar_one_or_none()
        if prop is None:
            return False
        prop.status = "sold"
        prop.sold_at = datetime.utcnow()
        await session.commit()
        return True


async def search_properties(
    property_type: str | None = None,
    rooms: int | None = None,
    price_max: int | None = None,
    price_min: int | None = None,
    district: str | None = None,
    area_min: int | None = None,
    area_max: int | None = None,
    text_query: str | None = None,
    limit: int | None = None,
) -> list[Property]:
    """Поиск объектов по фильтрам. Показывает только active."""
    async with async_session_factory() as session:
        stmt = select(Property).where(Property.status == "active")

        if property_type:
            stmt = stmt.where(Property.property_type == property_type)
        if rooms is not None:
            stmt = stmt.where(Property.rooms == rooms)
        if price_max is not None:
            stmt = stmt.where(Property.price <= price_max)
        if price_min is not None:
            stmt = stmt.where(Property.price >= price_min)
        if district:
            stmt = stmt.where(Property.district.ilike(f"%{district}%"))
        if area_min is not None:
            stmt = stmt.where(Property.area >= area_min)
        if area_max is not None:
            stmt = stmt.where(Property.area <= area_max)
        if text_query:
            pattern = f"%{text_query}%"
            stmt = stmt.where(
                or_(
                    Property.title.ilike(pattern),
                    Property.address.ilike(pattern),
                    Property.description.ilike(pattern),
                )
            )

        stmt = stmt.order_by(Property.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await session.execute(stmt)
        return list(result.scalars().all())
