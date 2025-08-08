from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from handlers.stats import get_period_keyboard  # вместо get_stats_keyboard

router = Router()

# 🔹 Главное меню
main_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💹 Получить сигналы", callback_data="signals")],
    [InlineKeyboardButton(text="🤖 Автоторговля", callback_data="trading_menu")],
    [InlineKeyboardButton(text="📈 Статистика", callback_data="stats_menu")],
    [InlineKeyboardButton(text="💳 Тарифы", callback_data="tariffs")],
])

# 🔹 Обработчик команды /start
@router.message(F.text == "/start")
async def start_command(message: Message):
    await message.answer(
        "👋 Привет! Я бот для трейдинга.\n\n"
        "Я могу присылать сигналы, показывать статистику и позже смогу торговать сам.\n\n"
        "Выбери, что хочешь сделать:",
        reply_markup=main_menu
    )

# 🔹 Когда нажали «Статистика» в главном меню
@router.callback_query(F.data == "stats_menu")
async def show_stats_menu(callback: CallbackQuery):
    await callback.message.answer("Выберите период для статистики:", reply_markup=get_period_keyboard())
    await callback.answer()

# 🔹 Обработчик нажатий на «Тарифы»
@router.callback_query(F.data == "tariffs")
async def show_tariffs(callback: CallbackQuery):
    await callback.message.answer(
        "💳 Доступные тарифы:\n"
        "1️⃣ 1 месяц — быстрый старт\n"
        "2️⃣ 3 месяца — продвинутый трейдинг\n"
        "3️⃣ 6 месяцев — полный курс с практикой\n\n"
        "Скоро добавим оплату прямо в боте!"
    )
    await callback.answer()

# 🔹 Обработчик нажатий на «Сигналы» (пока заглушка)
@router.callback_query(F.data == "signals")
async def show_signals(callback: CallbackQuery):
    await callback.message.answer(
        "📡 Сигналы приходят автоматически, как только бот находит подходящие возможности!"
    )
    await callback.answer()
