# handlers/autotrade.py
from aiogram import Router, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from db.database import (
    has_active_subscription, autotrade_paid, autotrade_enabled,
    get_user_settings, update_user_settings, set_api_keys
)

router = Router()

# ---------- клавиатуры ----------
def back_btn():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="main_menu")]
    ])

def autotrade_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    paid = autotrade_paid(user_id)
    enabled = autotrade_enabled(user_id)
    kb = []

    if paid:
        kb.append([InlineKeyboardButton(text=("⏸ Выключить автоторговлю" if enabled else "▶️ Включить автоторговлю"),
                                        callback_data=("auto_disable" if enabled else "auto_enable"))])
        kb.append([InlineKeyboardButton(text="🔑 Подключить/изменить API-ключи", callback_data="api_connect")])
        kb.append([
            InlineKeyboardButton(text="💥 Риск %", callback_data="risk_edit"),
            InlineKeyboardButton(text="⚖️ Плечо", callback_data="leverage_edit"),
        ])
        kb.append([
            InlineKeyboardButton(text="📦 Маржа", callback_data="margin_toggle"),
            InlineKeyboardButton(text="🔀 Режим позиции", callback_data="position_toggle"),
        ])
    else:
        kb.append([InlineKeyboardButton(text="💳 Оплатить автоторговлю", callback_data="autotrade_pay_stub")])

    kb.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ---------- состояния ввода ----------
class ApiForm(StatesGroup):
    key = State()
    secret = State()

class RiskForm(StatesGroup):
    value = State()

class LeverageForm(StatesGroup):
    value = State()

# ---------- утилиты ----------
def format_settings_text(user_id: int) -> str:
    s = get_user_settings(user_id)
    paid = autotrade_paid(user_id)
    enabled = autotrade_enabled(user_id)
    lines = [
        "🤖 <b>Автоторговля</b>",
        f"Статус оплаты: {'✅ оплачена' if paid else '❌ не оплачена'}",
        f"Состояние: {'▶️ включена' if enabled else '⏸ выключена'}",
        "",
        f"Риск на сделку: <b>{s['risk_pct']:.2f}%</b>",
        f"Плечо: <b>x{s['leverage']}</b>",
        f"Маржа: <b>{s['margin_mode']}</b>",
        f"Режим позиции: <b>{s['position_mode']}</b>",
        "",
        "Здесь вы можете управлять настройками и ключами.",
    ]
    return "\n".join(lines)

# ---------- вход в раздел автоторговли ----------
@router.callback_query(F.data == "trading_menu")
async def show_autotrade_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not has_active_subscription(user_id):
        await callback.message.edit_text(
            "Чтобы пользоваться автоторговлей, нужна активная подписка на сигналы.\n"
            "Оформите её в «💹 Получить сигналы».",
            reply_markup=back_btn()
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        format_settings_text(user_id),
        reply_markup=autotrade_menu_kb(user_id),
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- оплатить автоторговлю (заглушка) ----------
@router.callback_query(F.data == "autotrade_pay_stub")
async def autotrade_pay_stub(callback: CallbackQuery):
    await callback.message.edit_text(
        "💳 Оплата автоторговли скоро будет доступна прямо в боте.\n\n"
        "Пока для теста можно использовать команду /auto_pay30 (админ).",
        reply_markup=back_btn()
    )
    await callback.answer()

# ---------- вкл/выкл (будет работать после оплаты) ----------
from db.database import toggle_autotrade
@router.callback_query(F.data == "auto_enable")
async def auto_enable(callback: CallbackQuery):
    user_id = callback.from_user.id
    toggle_autotrade(user_id, True)
    await callback.message.edit_text(
        format_settings_text(user_id),
        reply_markup=autotrade_menu_kb(user_id),
        parse_mode="HTML"
    )
    await callback.answer("Автоторговля включена")

@router.callback_query(F.data == "auto_disable")
async def auto_disable(callback: CallbackQuery):
    user_id = callback.from_user.id
    toggle_autotrade(user_id, False)
    await callback.message.edit_text(
        format_settings_text(user_id),
        reply_markup=autotrade_menu_kb(user_id),
        parse_mode="HTML"
    )
    await callback.answer("Автоторговля выключена")

# ---------- ввод API-ключей ----------
@router.callback_query(F.data == "api_connect")
async def api_connect_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ApiForm.key)
    await callback.message.edit_text(
        "🔑 Отправьте <b>API Key</b> одной строкой.",
        reply_markup=back_btn(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(ApiForm.key)
async def api_key_entered(message: Message, state: FSMContext):
    await state.update_data(api_key=message.text.strip())
    await state.set_state(ApiForm.secret)
    await message.answer("Теперь отправьте <b>API Secret</b>.", parse_mode="HTML")

@router.message(ApiForm.secret)
async def api_secret_entered(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("api_key")
    secret = message.text.strip()
    set_api_keys(message.from_user.id, key, secret)
    await state.clear()
    await message.answer("✅ Ключи сохранены. Вернитесь в «🤖 Автоторговля» для управления.", reply_markup=back_btn())

# ---------- правка риска ----------
@router.callback_query(F.data == "risk_edit")
async def risk_edit(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RiskForm.value)
    await callback.message.edit_text("Укажите риск на сделку в % (например: 1.0)", reply_markup=back_btn())
    await callback.answer()

@router.message(RiskForm.value)
async def risk_save(message: Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        assert 0 < val <= 10
    except Exception:
        await message.answer("⚠️ Введите число от 0.1 до 10. Пример: 1.0")
        return
    update_user_settings(message.from_user.id, risk_pct=val)
    await state.clear()
    await message.answer("✅ Риск сохранён. Откройте «🤖 Автоторговля», чтобы увидеть изменения.", reply_markup=back_btn())

# ---------- правка плеча ----------
@router.callback_query(F.data == "leverage_edit")
async def leverage_edit(callback: CallbackQuery, state: FSMContext):
    await state.set_state(LeverageForm.value)
    await callback.message.edit_text("Введите плечо (1–50). Пример: 5", reply_markup=back_btn())
    await callback.answer()

@router.message(LeverageForm.value)
async def leverage_save(message: Message, state: FSMContext):
    try:
        lev = int(message.text)
        assert 1 <= lev <= 50
    except Exception:
        await message.answer("⚠️ Введите целое число от 1 до 50.")
        return
    update_user_settings(message.from_user.id, leverage=lev)
    await state.clear()
    await message.answer("✅ Плечо сохранено. Откройте «🤖 Автоторговля», чтобы увидеть изменения.", reply_markup=back_btn())

# ---------- переключатели режимов ----------
@router.callback_query(F.data == "margin_toggle")
async def margin_toggle(callback: CallbackQuery):
    user_id = callback.from_user.id
    s = get_user_settings(user_id)
    new_mode = "CROSS" if s["margin_mode"] == "ISOLATED" else "ISOLATED"
    update_user_settings(user_id, margin_mode=new_mode)
    await callback.message.edit_text(
        format_settings_text(user_id), reply_markup=autotrade_menu_kb(user_id), parse_mode="HTML"
    )
    await callback.answer(f"Маржа: {new_mode}")

@router.callback_query(F.data == "position_toggle")
async def position_toggle(callback: CallbackQuery):
    user_id = callback.from_user.id
    s = get_user_settings(user_id)
    new_mode = "HEDGE" if s["position_mode"] == "ONEWAY" else "ONEWAY"
    update_user_settings(user_id, position_mode=new_mode)
    await callback.message.edit_text(
        format_settings_text(user_id), reply_markup=autotrade_menu_kb(user_id), parse_mode="HTML"
    )
    await callback.answer(f"Режим позиции: {new_mode}")
