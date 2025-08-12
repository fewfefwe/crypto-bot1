from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from handlers.stats import get_period_keyboard  # твой существующий клавиатурный хелпер
from db.database import (
    has_active_subscription, get_subscription_expiry,
    autotrade_paid, autotrade_enabled
)
from datetime import datetime

router = Router()

# ========= Клавиатуры =========
def get_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💹 Получить сигналы", callback_data="signals")],
        [InlineKeyboardButton(text="🤖 Автоторговля", callback_data="trading_menu")],
        [InlineKeyboardButton(text="📈 Статистика", callback_data="stats_menu")],
        [InlineKeyboardButton(text="💳 Тарифы", callback_data="tariffs")],
    ])

def back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="main_menu")]
    ])

def signals_tariffs_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 неделя",  callback_data="buy_signals_week"),
            InlineKeyboardButton(text="1 месяц",   callback_data="buy_signals_month"),
            InlineKeyboardButton(text="3 месяца",  callback_data="buy_signals_quarter"),
        ],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="main_menu")]
    ])

def signals_subscribed_kb(user_id: int) -> InlineKeyboardMarkup:
    paid = autotrade_paid(user_id)
    kb = [
        [
            InlineKeyboardButton(
                text=("⚙️ Настройки автоторговли" if paid else "🤖 Подключить автоторговлю"),
                callback_data=("autotrade_settings" if paid else "autotrade_connect")
            )
        ],
        [InlineKeyboardButton(text="➕ Продлить подписку", callback_data="signals_extend")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ========= Утилиты =========
def _format_expiry(dt: datetime | None) -> str:
    if not dt:
        return "неизвестно"
    return dt.strftime("%d.%m.%Y %H:%M")

# ========= Хэндлеры =========
@router.message(F.text == "/start")
async def start_command(message: Message):
    await message.answer(
        "👋 Привет! Я бот для трейдинга.\n\n"
        "Я могу присылать сигналы, показывать статистику и торговать сам (по желанию).\n\n"
        "Выбери, что хочешь сделать:",
        reply_markup=get_main_menu()
    )

@router.callback_query(F.data == "main_menu")
async def go_main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "👋 Привет! Я бот для трейдинга.\n\n"
        "Выбери, что хочешь сделать:",
        reply_markup=get_main_menu()
    )
    await callback.answer()

# --- Получить сигналы ---
@router.callback_query(F.data == "signals")
async def show_signals_entry(callback: CallbackQuery):
    user_id = callback.from_user.id

    if has_active_subscription(user_id):
        expiry = get_subscription_expiry(user_id)
        text = (
            "✅ Подписка на сигналы активна.\n"
            f"⏳ Действует до: <b>{_format_expiry(expiry)}</b>\n\n"
            "Бот будет автоматически присылать сигналы в этот чат.\n"
            "Дополнительно вы можете подключить автоторговлю:"
        )
        # по твоему запросу — отправляем НОВОЕ сообщение
        await callback.message.answer(text, reply_markup=signals_subscribed_kb(user_id), parse_mode="HTML")
    else:
        text = (
            "📡 Чтобы бот присылал вам сигналы, нужно оформить подписку из вариантов ниже.\n\n"
            "После оплаты бот будет автоматически присылать сигналы в этот чат.\n\n"
            "Выберите тариф:"
        )
        await callback.message.answer(text, reply_markup=signals_tariffs_kb())

    await callback.answer()

# --- Заглушки покупки тарифов (подключим оплату позже) ---
@router.callback_query(F.data == "buy_signals_week")
async def buy_signals_week(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("🧾 Тариф «1 неделя». Оплата скоро будет доступна в боте.", reply_markup=back_button())

@router.callback_query(F.data == "buy_signals_month")
async def buy_signals_month(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("🧾 Тариф «1 месяц». Оплата скоро будет доступна в боте.", reply_markup=back_button())

@router.callback_query(F.data == "buy_signals_quarter")
async def buy_signals_quarter(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("🧾 Тариф «3 месяца». Оплата скоро будет доступна в боте.", reply_markup=back_button())

# --- Статистика ---
@router.callback_query(F.data == "stats_menu")
async def show_stats_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выберите период для статистики:",
        reply_markup=get_period_keyboard()
    )
    await callback.answer()

# --- Общие тарифы (инфо) ---
@router.callback_query(F.data == "tariffs")
async def show_tariffs(callback: CallbackQuery):
    await callback.message.edit_text(
        "💳 Общие тарифы (инфо-экран). Для сигналов используйте «💹 Получить сигналы».",
        reply_markup=back_button()
    )
    await callback.answer()

# --- Автоторговля (заглушки: дальше добавим управление и ввод API) ---
@router.callback_query(F.data == "autotrade_connect")
async def autotrade_connect(callback: CallbackQuery):
    await callback.message.edit_text(
        "🤖 Подключение автоторговли.\n\nСкоро тут можно будет привязать API и оплатить автоторговлю.",
        reply_markup=back_button()
    )
    await callback.answer()

@router.callback_query(F.data == "autotrade_settings")
async def autotrade_settings(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚙️ Настройки автоторговли.\n\nСкоро здесь появятся переключатели: Вкл/Выкл, риск %, плечо, маржа, режим позиции.",
        reply_markup=back_button()
    )
    await callback.answer()

@router.callback_query(F.data == "trading_menu")
async def show_trading_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "🤖 Раздел автоторговли.\n\nСкоро тут можно будет включить торговлю и настроить параметры.",
        reply_markup=back_button()
    )
    await callback.answer()
