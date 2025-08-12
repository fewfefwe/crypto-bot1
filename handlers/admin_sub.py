# handlers/admin_sub.py
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
# handlers/admin_sub.py
from db.database import activate_subscription, set_autotrade_paid, toggle_autotrade, add_user

from config import ADMIN_CHAT_ID
from db.database import (
    activate_subscription, set_autotrade_paid, toggle_autotrade
)

router = Router()

def _is_admin(user_id: int) -> bool:
    return str(user_id) == str(ADMIN_CHAT_ID)

def _target_user_id(msg: Message) -> int:
    # можно выдавать себе или по reply на сообщение пользователя
    return msg.reply_to_message.from_user.id if msg.reply_to_message else msg.from_user.id

@router.message(Command("sub_week"))
async def sub_week(message: Message):
    if not _is_admin(message.from_user.id): return
    uid = _target_user_id(message)
    uname = message.reply_to_message.from_user.username if message.reply_to_message else message.from_user.username
    add_user(uid, uname or "")              # ← гарантируем, что user есть
    activate_subscription(uid, "WEEK", 0.0)
    await message.answer(f"✅ Выдал подписку на 1 неделю пользователю {uid}")


@router.message(Command("sub_month"))
async def sub_month(message: Message):
    if not _is_admin(message.from_user.id): return
    uid = _target_user_id(message)
    uname = message.reply_to_message.from_user.username if message.reply_to_message else message.from_user.username
    add_user(uid, uname or "")
    activate_subscription(uid, "MONTH", amount=0.0)
    await message.answer(f"✅ Выдал подписку на 1 месяц пользователю {uid}")

@router.message(Command("sub_quarter"))
async def sub_quarter(message: Message):
    if not _is_admin(message.from_user.id): return
    uid = _target_user_id(message)
    uname = message.reply_to_message.from_user.username if message.reply_to_message else message.from_user.username
    add_user(uid, uname or "")
    activate_subscription(uid, "QUARTER", amount=0.0)
    await message.answer(f"✅ Выдал подписку на 3 месяца пользователю {uid}")

@router.message(Command("auto_pay30"))
async def auto_pay30(message: Message):
    if not _is_admin(message.from_user.id):
        return
    uid = _target_user_id(message)
    set_autotrade_paid(uid, days=30)
    await message.answer(f"✅ Оплачена автоторговля на 30 дней для {uid}")

@router.message(Command("auto_on"))
async def auto_on(message: Message):
    if not _is_admin(message.from_user.id):
        return
    uid = _target_user_id(message)
    toggle_autotrade(uid, True)
    await message.answer(f"▶️ Автоторговля включена для {uid}")

@router.message(Command("auto_off"))
async def auto_off(message: Message):
    if not _is_admin(message.from_user.id):
        return
    uid = _target_user_id(message)
    toggle_autotrade(uid, False)
    await message.answer(f"⏸ Автоторговля выключена для {uid}")
