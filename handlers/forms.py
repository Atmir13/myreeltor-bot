"""FSM-формы подачи объявления и заявки на поиск."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart
from aiogram.types import Message

from database import UserListing, async_session_factory
from services.moderation import auto_moderate


router = Router()
logger = logging.getLogger(__name__)


class SellForm(StatesGroup):
    waiting_title = State()
    waiting_price = State()
    waiting_rooms = State()
    waiting_area = State()
    waiting_address = State()
    waiting_description = State()
    waiting_contact = State()


class BuyForm(StatesGroup):
    waiting_type = State()
    waiting_rooms = State()
    waiting_price = State()
    waiting_district = State()
    waiting_contact = State()


def _number(value: str) -> int | None:
    try:
        return int(float(value.replace(" ", "").replace(",", "."))) or None
    except (ValueError, TypeError):
        return None


async def _create_listing(telegram_id: int, listing_type: str, data: dict) -> int:
    async with async_session_factory() as session:
        listing = UserListing(telegram_id=telegram_id, type=listing_type, **data)
        session.add(listing)
        await session.commit()
        await session.refresh(listing)
        return listing.id


@router.message(SellForm.waiting_title)
async def sell_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text or "")
    await state.set_state(SellForm.waiting_price)
    await message.answer("Укажите цену в рублях:")


@router.message(SellForm.waiting_price)
async def sell_price(message: Message, state: FSMContext) -> None:
    await state.update_data(price=_number(message.text or ""))
    await state.set_state(SellForm.waiting_rooms)
    await message.answer("Сколько комнат? Если неважно — 0:")


@router.message(SellForm.waiting_rooms)
async def sell_rooms(message: Message, state: FSMContext) -> None:
    await state.update_data(rooms=_number(message.text or ""))
    await state.set_state(SellForm.waiting_area)
    await message.answer("Площадь в м²:")


@router.message(SellForm.waiting_area)
async def sell_area(message: Message, state: FSMContext) -> None:
    await state.update_data(area=_number(message.text or ""))
    await state.set_state(SellForm.waiting_address)
    await message.answer("Адрес или район:")


@router.message(SellForm.waiting_address)
async def sell_address(message: Message, state: FSMContext) -> None:
    await state.update_data(address=message.text or "")
    await state.set_state(SellForm.waiting_description)
    await message.answer("Опишите объект:")


@router.message(SellForm.waiting_description)
async def sell_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text or "")
    await state.set_state(SellForm.waiting_contact)
    await message.answer("Оставьте телефон или Telegram для связи:")


@router.message(SellForm.waiting_contact)
async def sell_contact(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    data["contact"] = message.text or ""
    listing_id = await _create_listing(message.from_user.id, "sell", data)
    await state.clear()
    await message.answer("✅ Объявление принято! Оно появится в канале после проверки.")
    await auto_moderate(listing_id, message.bot)


@router.message(BuyForm.waiting_type)
async def buy_type(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text or "")
    await state.set_state(BuyForm.waiting_rooms)
    await message.answer("Сколько комнат нужно?")


@router.message(BuyForm.waiting_rooms)
async def buy_rooms(message: Message, state: FSMContext) -> None:
    await state.update_data(rooms=_number(message.text or ""))
    await state.set_state(BuyForm.waiting_price)
    await message.answer("Какой бюджет в рублях?")


@router.message(BuyForm.waiting_price)
async def buy_price(message: Message, state: FSMContext) -> None:
    await state.update_data(price=_number(message.text or ""))
    await state.set_state(BuyForm.waiting_district)
    await message.answer("В каком городе или районе ищете?")


@router.message(BuyForm.waiting_district)
async def buy_district(message: Message, state: FSMContext) -> None:
    await state.update_data(district=message.text or "")
    await state.set_state(BuyForm.waiting_contact)
    await message.answer("Оставьте телефон или Telegram для связи:")


@router.message(BuyForm.waiting_contact)
async def buy_contact(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    data["contact"] = message.text or ""
    listing_id = await _create_listing(message.from_user.id, "buy", data)
    await state.clear()
    await message.answer("✅ Заявка принята! Мы сообщим после проверки.")
    await auto_moderate(listing_id, message.bot)
