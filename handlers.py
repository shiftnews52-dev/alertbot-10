"""
handlers.py - Обработчики команд с интеграцией платежей
"""
from aiogram import Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from database import (
    add_user, get_user_lang, set_user_lang, is_paid, get_user_pairs,
    add_user_pair, remove_user_pair, get_balance, grant_access, revoke_access,
    get_total_users, get_paid_users_count, get_all_paid_users, get_subscription_info,
    db_pool, user_exists
)
from config import ADMIN_IDS, SUPPORT_URL, DEFAULT_PAIRS
from payment_handlers import show_payment_menu, handle_plan_selection, handle_payment_check
import logging

logger = logging.getLogger(__name__)

# ==================== ВЫБОР ЯЗЫКА ====================
async def show_language_selection(message: types.Message, invited_by: int = None):
    """Показать выбор языка для нового пользователя"""
    text = "🌍 <b>Choose your language / Выберите язык</b>\n\n"
    text += "Please select your preferred language:\n"
    text += "Пожалуйста, выберите предпочитаемый язык:"
    
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🇬🇧 English", callback_data=f"lang_en_{invited_by if invited_by else 0}"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data=f"lang_ru_{invited_by if invited_by else 0}")
    )
    
    await message.answer(text, reply_markup=kb)

async def handle_language_selection(call: types.CallbackQuery):
    """Обработка выбора языка"""
    user_id = call.from_user.id
    data = call.data.split("_")
    lang = data[1]  # en или ru
    invited_by = int(data[2]) if data[2] != "0" else None
    
    # Добавляем пользователя с выбранным языком
    await add_user(user_id, lang=lang, invited_by=invited_by)
    
    # Показываем приветствие
    await call.message.delete()
    await show_welcome_message(call.message, user_id, lang)
    await call.answer()

async def show_welcome_message(message: types.Message, user_id: int, lang: str):
    """Показать приветственное сообщение после выбора языка"""
    paid = await is_paid(user_id)
    
    # Приветствие
    if lang == "en":
        text = "🚀 <b>Welcome to Alpha Entry Bot!</b>\n\n"
        text += "⏰ Hourly signals with automatic TP/SL\n\n"
        text += "• 3-5 quality signals per day\n"
        text += "• Multi-strategy (5+ indicators)\n"
        text += "• Explanation for each entry\n"
        text += "• Volume and volatility filtering\n\n"
        
        if paid:
            sub_info = await get_subscription_info(user_id)
            if sub_info and sub_info["is_active"]:
                text += f"✅ <b>Premium active until</b>\n"
                text += f"   {sub_info['expiry_date'].strftime('%d.%m.%Y')}\n"
                text += f"   Days left: {sub_info['days_left']}\n\n"
        else:
            text += "🔓 Click <b>Get Access</b> to start receiving signals\n"
            text += "🎁 Or enter a <b>Promo Code</b> for free access\n\n"
        
        text += "📖 Click <b>Guide</b> for details"
    else:
        text = "🚀 <b>Добро пожаловать в Alpha Entry Bot!</b>\n\n"
        text += "⏰ Часовые сигналы с автоматическим TP/SL\n\n"
        text += "• 3-5 качественных сигналов в день\n"
        text += "• Мультистратегия (5+ индикаторов)\n"
        text += "• Объяснение каждого входа\n"
        text += "• Фильтрация по объёму и волатильности\n\n"
        
        if paid:
            sub_info = await get_subscription_info(user_id)
            if sub_info and sub_info["is_active"]:
                text += f"✅ <b>Premium активна до</b>\n"
                text += f"   {sub_info['expiry_date'].strftime('%d.%m.%Y')}\n"
                text += f"   Осталось дней: {sub_info['days_left']}\n\n"
        else:
            text += "🔓 Жми <b>Открыть доступ</b> чтобы получать сигналы\n"
            text += "🎁 Или введи <b>Промокод</b> для бесплатного доступа\n\n"
        
        text += "📖 Жми <b>Инструкция</b> для деталей"
    
    kb = await get_main_menu(user_id)
    await message.answer(text, reply_markup=kb)

# ==================== ГЛАВНОЕ МЕНЮ ====================
async def get_main_menu(user_id: int):
    """Получить главное меню"""
    lang = await get_user_lang(user_id)
    paid = await is_paid(user_id)
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    if lang == "en":
        if paid:
            kb.add(
                KeyboardButton("📈 Alerts"),
                KeyboardButton("👥 Referrals")
            )
            kb.add(
                KeyboardButton("📖 Guide"),
                KeyboardButton("💬 Support")
            )
            kb.add(KeyboardButton("📊 Statistics"))
        else:
            kb.add(
                KeyboardButton("🔓 Get Access"),
                KeyboardButton("🎁 Promo Code")
            )
            kb.add(
                KeyboardButton("📖 Guide"),
                KeyboardButton("💬 Support")
            )
    else:
        if paid:
            kb.add(
                KeyboardButton("📈 Алерты"),
                KeyboardButton("👥 Рефералка")
            )
            kb.add(
                KeyboardButton("📖 Инструкция"),
                KeyboardButton("💬 Поддержка")
            )
            kb.add(KeyboardButton("📊 Статистика"))
        else:
            kb.add(
                KeyboardButton("🔓 Открыть доступ"),
                KeyboardButton("🎁 Промокод")
            )
            kb.add(
                KeyboardButton("📖 Инструкция"),
                KeyboardButton("💬 Поддержка")
            )
    
    return kb

# ==================== КОМАНДА /START ====================
async def cmd_start(message: types.Message):
    """Команда /start"""
    user_id = message.from_user.id
    
    # Проверяем реферальную ссылку
    args = message.get_args()
    invited_by = None
    if args and args.isdigit():
        invited_by = int(args)
    
    # Проверяем существует ли пользователь
    is_new_user = not await user_exists(user_id)
    
    if is_new_user:
        # Новый пользователь - показываем выбор языка
        await show_language_selection(message, invited_by)
        return
    
    # Существующий пользователь - продолжаем как обычно
    lang = await get_user_lang(user_id)
    paid = await is_paid(user_id)
    
    # Приветствие
    if lang == "en":
        text = "🚀 <b>Alpha Entry Bot</b>\n\n"
        text += "⏰ Hourly signals with automatic TP/SL\n\n"
        text += "• 3-5 quality signals per day\n"
        text += "• Multi-strategy (5+ indicators)\n"
        text += "• Explanation for each entry\n"
        text += "• Volume and volatility filtering\n\n"
        
        if paid:
            # Показываем информацию о подписке
            sub_info = await get_subscription_info(user_id)
            if sub_info and sub_info["is_active"]:
                text += f"✅ <b>Premium active until</b>\n"
                text += f"   {sub_info['expiry_date'].strftime('%d.%m.%Y')}\n"
                text += f"   Days left: {sub_info['days_left']}\n\n"
        else:
            text += "🔓 Click <b>Get Access</b> to start receiving signals\n\n"
        
        text += "📖 Click <b>Guide</b> for details"
    else:
        text = "🚀 <b>Alpha Entry Bot</b>\n\n"
        text += "⏰ Часовые сигналы с автоматическим TP/SL\n\n"
        text += "• 3-5 качественных сигналов в день\n"
        text += "• Мультистратегия (5+ индикаторов)\n"
        text += "• Объяснение каждого входа\n"
        text += "• Фильтрация по объёму и волатильности\n\n"
        
        if paid:
            # Показываем информацию о подписке
            sub_info = await get_subscription_info(user_id)
            if sub_info and sub_info["is_active"]:
                text += f"✅ <b>Premium активна до</b>\n"
                text += f"   {sub_info['expiry_date'].strftime('%d.%m.%Y')}\n"
                text += f"   Осталось дней: {sub_info['days_left']}\n\n"
        else:
            text += "🔓 Жми <b>Открыть доступ</b> чтобы получать сигналы\n\n"
        
        text += "📖 Жми <b>Инструкция</b> для деталей"
    
    kb = await get_main_menu(user_id)
    await message.answer(text, reply_markup=kb)

# ==================== МЕНЮ АЛЕРТОВ ====================
async def show_alerts_menu(message: types.Message):
    """Показать меню управления алертами"""
    user_id = message.from_user.id
    lang = await get_user_lang(user_id)
    paid = await is_paid(user_id)
    
    if not paid:
        error_text = "❌ Access required. Click 🔓 Get Access" if lang == "en" else "❌ Нужен доступ. Нажми 🔓 Открыть доступ"
        await message.answer(error_text)
        return
    
    user_pairs = await get_user_pairs(user_id)
    
    if lang == "en":
        text = "📈 <b>Alert Settings</b>\n\n"
        text += f"Active pairs: {len(user_pairs)}/10\n\n"
        if user_pairs:
            text += "Your pairs:\n"
            for pair in user_pairs:
                text += f"• {pair}\n"
        else:
            text += "No active pairs yet.\nAdd pairs below."
    else:
        text = "📈 <b>Настройки алертов</b>\n\n"
        text += f"Активных пар: {len(user_pairs)}/10\n\n"
        if user_pairs:
            text += "Твои пары:\n"
            for pair in user_pairs:
                text += f"• {pair}\n"
        else:
            text += "Нет активных пар.\nДобавь пары ниже."
    
    kb = InlineKeyboardMarkup(row_width=2)
    
    # Кнопки добавления пар
    for pair in DEFAULT_PAIRS:
        is_active = pair in user_pairs
        emoji = "✅" if is_active else "➕"
        callback = f"remove_{pair}" if is_active else f"add_{pair}"
        kb.insert(InlineKeyboardButton(f"{emoji} {pair}", callback_data=callback))
    
    # Кнопка назад
    back_text = "⬅️ Back" if lang == "en" else "⬅️ Назад"
    kb.add(InlineKeyboardButton(back_text, callback_data="back_main"))
    
    await message.answer(text, reply_markup=kb)

# ==================== ИНСТРУКЦИЯ ====================
async def show_guide(message: types.Message):
    """Показать инструкцию"""
    lang = await get_user_lang(message.from_user.id)
    
    if lang == "en":
        text = "📖 <b>How to use the bot</b>\n\n"
        text += "<b>1. Get Access</b>\n"
        text += "Click 🔓 Get Access and choose a plan\n\n"
        text += "<b>2. Add Pairs</b>\n"
        text += "Go to 📈 Alerts and add up to 10 pairs\n\n"
        text += "<b>3. Receive Signals</b>\n"
        text += "Bot will send 3-5 signals per day\n"
        text += "Each signal contains:\n"
        text += "• Entry price\n"
        text += "• 3 Take Profit levels\n"
        text += "• Stop Loss\n"
        text += "• Reasoning\n\n"
        text += "<b>4. Risk Management</b>\n"
        text += "• Never risk more than 2% per trade\n"
        text += "• Always use Stop Loss\n"
        text += "• Take partial profits at TP levels\n\n"
        text += "<b>Timeframe:</b> 1 hour\n"
        text += "<b>Max signals:</b> 3 per day per pair\n"
        text += "<b>Min score:</b> 70/100\n\n"
        text += "💬 Questions? Click Support"
    else:
        text = "📖 <b>Как пользоваться ботом</b>\n\n"
        text += "<b>1. Открыть доступ</b>\n"
        text += "Нажми 🔓 Открыть доступ и выбери тариф\n\n"
        text += "<b>2. Добавить пары</b>\n"
        text += "Зайди в 📈 Алерты и добавь до 10 пар\n\n"
        text += "<b>3. Получать сигналы</b>\n"
        text += "Бот будет присылать 3-5 сигналов в день\n"
        text += "Каждый сигнал содержит:\n"
        text += "• Цену входа\n"
        text += "• 3 уровня Take Profit\n"
        text += "• Stop Loss\n"
        text += "• Обоснование\n\n"
        text += "<b>4. Управление рисками</b>\n"
        text += "• Никогда не рискуй > 2% на сделку\n"
        text += "• Всегда используй Stop Loss\n"
        text += "• Забирай частичную прибыль на TP\n\n"
        text += "<b>Таймфрейм:</b> 1 час\n"
        text += "<b>Макс. сигналов:</b> 3 в день на пару\n"
        text += "<b>Мин. score:</b> 70/100\n\n"
        text += "💬 Вопросы? Нажми Поддержка"
    
    await message.answer(text)

# ==================== ПОДДЕРЖКА ====================
async def show_support(message: types.Message):
    """Показать контакты поддержки"""
    lang = await get_user_lang(message.from_user.id)
    
    if lang == "en":
        text = "💬 <b>Support</b>\n\n"
        text += "Have questions or issues?\n"
        text += "Contact us:"
    else:
        text = "💬 <b>Поддержка</b>\n\n"
        text += "Есть вопросы или проблемы?\n"
        text += "Свяжись с нами:"
    
    kb = InlineKeyboardMarkup()
    support_text = "✉️ Contact Support" if lang == "en" else "✉️ Написать в поддержку"
    kb.add(InlineKeyboardButton(support_text, url=SUPPORT_URL))
    
    await message.answer(text, reply_markup=kb)

# ==================== ПРОМОКОДЫ ====================
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

class PromoStates(StatesGroup):
    waiting_for_promo = State()

PROMO_CODES = {
    "1550": {
        "type": "full_access",
        "duration_days": 365 * 100,  # Практически навсегда
        "max_uses": None,  # Неограниченно
        "description": "VIP промокод"
    }
}

# Счётчик использований промокодов
promo_usage = {}

async def show_promo_input(message: types.Message, state: FSMContext):
    """Показать запрос на ввод промокода"""
    lang = await get_user_lang(message.from_user.id)
    
    if lang == "en":
        text = "🎁 <b>Enter Promo Code</b>\n\n"
        text += "Enter your promo code to get free access:\n\n"
        text += "Send the code or click Cancel to return to menu."
    else:
        text = "🎁 <b>Введи промокод</b>\n\n"
        text += "Введи промокод чтобы получить бесплатный доступ:\n\n"
        text += "Отправь код или нажми Отмена чтобы вернуться в меню."
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    cancel_text = "❌ Cancel" if lang == "en" else "❌ Отмена"
    kb.add(KeyboardButton(cancel_text))
    
    await message.answer(text, reply_markup=kb)
    await PromoStates.waiting_for_promo.set()

async def handle_promo_code(message: types.Message, state: FSMContext):
    """Обработка введённого промокода"""
    user_id = message.from_user.id
    lang = await get_user_lang(user_id)
    promo_code = message.text.strip()
    
    # Проверка на отмену
    if promo_code in ["❌ Cancel", "❌ Отмена"]:
        await state.finish()
        kb = await get_main_menu(user_id)
        cancel_text = "Cancelled" if lang == "en" else "Отменено"
        await message.answer(cancel_text, reply_markup=kb)
        return
    
    # Проверяем промокод
    if promo_code in PROMO_CODES:
        promo = PROMO_CODES[promo_code]
        
        # Проверяем лимит использований
        if promo["max_uses"] is not None:
            uses = promo_usage.get(promo_code, 0)
            if uses >= promo["max_uses"]:
                error_text = "❌ This promo code has reached its usage limit" if lang == "en" else "❌ Этот промокод исчерпал лимит использований"
                await message.answer(error_text)
                await state.finish()
                kb = await get_main_menu(user_id)
                await message.answer("👌", reply_markup=kb)
                return
        
        # Проверяем не использовал ли уже этот пользователь промокод
        conn = await db_pool.acquire()
        try:
            cursor = await conn.execute(
                "SELECT paid FROM users WHERE id=?",
                (user_id,)
            )
            row = await cursor.fetchone()
            if row and row[0] == 1:
                already_text = "✅ You already have access!" if lang == "en" else "✅ У тебя уже есть доступ!"
                await message.answer(already_text)
                await state.finish()
                kb = await get_main_menu(user_id)
                await message.answer("👌", reply_markup=kb)
                return
        finally:
            await db_pool.release(conn)
        
        # Выдаём доступ
        from datetime import datetime, timedelta
        from crypto_payment import grant_subscription_access
        
        await grant_subscription_access(user_id, "promo_" + promo_code)
        
        # Устанавливаем срок действия
        expiry_date = datetime.now() + timedelta(days=promo["duration_days"])
        conn = await db_pool.acquire()
        try:
            await conn.execute(
                "UPDATE users SET subscription_expiry=?, subscription_plan=? WHERE id=?",
                (int(expiry_date.timestamp()), f"promo_{promo_code}", user_id)
            )
            await conn.commit()
        finally:
            await db_pool.release(conn)
        
        # Увеличиваем счётчик использований
        promo_usage[promo_code] = promo_usage.get(promo_code, 0) + 1
        
        # Уведомление
        if lang == "en":
            text = "🎉 <b>Promo Code Activated!</b>\n\n"
            text += f"✅ Access granted\n"
            text += f"📅 Valid until: {expiry_date.strftime('%d.%m.%Y')}\n\n"
            text += f"Use /start to begin receiving signals!"
        else:
            text = "🎉 <b>Промокод активирован!</b>\n\n"
            text += f"✅ Доступ выдан\n"
            text += f"📅 Действует до: {expiry_date.strftime('%d.%m.%Y')}\n\n"
            text += f"Используй /start чтобы начать получать сигналы!"
        
        await state.finish()
        kb = await get_main_menu(user_id)
        await message.answer(text, reply_markup=kb)
        
        logger.info(f"Promo code {promo_code} activated for user {user_id}")
    else:
        # Неверный промокод
        error_text = "❌ Invalid promo code. Try again or click Cancel." if lang == "en" else "❌ Неверный промокод. Попробуй снова или нажми Отмена."
        await message.answer(error_text)

# ==================== СТАТИСТИКА ====================
async def show_stats(message: types.Message):
    """Показать статистику пользователя"""
    user_id = message.from_user.id
    lang = await get_user_lang(user_id)
    paid = await is_paid(user_id)
    
    if not paid:
        error_text = "❌ Access required" if lang == "en" else "❌ Нужен доступ"
        await message.answer(error_text)
        return
    
    # TODO: Реализовать получение статистики из PnL системы
    if lang == "en":
        text = "📊 <b>Your Statistics</b>\n\n"
        text += "Coming soon...\n"
        text += "Statistics will include:\n"
        text += "• Win rate\n"
        text += "• Average profit/loss\n"
        text += "• Best/worst trades\n"
        text += "• TP/SL distribution"
    else:
        text = "📊 <b>Твоя статистика</b>\n\n"
        text += "Скоро...\n"
        text += "Статистика будет включать:\n"
        text += "• Винрейт\n"
        text += "• Средняя прибыль/убыток\n"
        text += "• Лучшие/худшие сделки\n"
        text += "• Распределение по TP/SL"
    
    await message.answer(text)

# ==================== АДМИН ПАНЕЛЬ ====================
async def show_admin_panel(message: types.Message):
    """Админ панель"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        return
    
    total_users = await get_total_users()
    paid_users = await get_paid_users_count()
    
    text = "👑 <b>Admin Panel</b>\n\n"
    text += f"📊 Total users: {total_users}\n"
    text += f"💎 Paid users: {paid_users}\n"
    text += f"📈 Conversion: {(paid_users/total_users*100) if total_users > 0 else 0:.1f}%\n"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"))
    kb.add(InlineKeyboardButton("✅ Grant Access", callback_data="admin_grant"))
    kb.add(InlineKeyboardButton("❌ Revoke Access", callback_data="admin_revoke"))
    
    await message.answer(text, reply_markup=kb)

# ==================== CALLBACK ОБРАБОТЧИКИ ====================
async def handle_callbacks(call: types.CallbackQuery):
    """Обработка callback кнопок"""
    user_id = call.from_user.id
    data = call.data
    
    # Добавление/удаление пар
    if data.startswith("add_"):
        pair = data.split("_")[1]
        await add_user_pair(user_id, pair)
        await show_alerts_menu(call.message)
        await call.answer("✅")
    
    elif data.startswith("remove_"):
        pair = data.split("_")[1]
        await remove_user_pair(user_id, pair)
        await show_alerts_menu(call.message)
        await call.answer("❌")
    
    # Возврат в главное меню
    elif data == "back_main":
        lang = await get_user_lang(user_id)
        text = "👌 OK" if lang == "en" else "👌 Хорошо"
        await call.message.delete()
        await call.answer(text)
    
    # Админ: выдать доступ
    elif data == "admin_grant":
        if user_id not in ADMIN_IDS:
            await call.answer("❌ Access denied")
            return
        await call.message.answer("Send user ID to grant access:")
        # TODO: Реализовать FSM для получения ID
    
    # Админ: отозвать доступ
    elif data == "admin_revoke":
        if user_id not in ADMIN_IDS:
            await call.answer("❌ Access denied")
            return
        await call.message.answer("Send user ID to revoke access:")
        # TODO: Реализовать FSM для получения ID

# ==================== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ====================
def setup_handlers(dp: Dispatcher):
    """Регистрация всех обработчиков"""
    
    # Команды
    dp.register_message_handler(cmd_start, commands=["start"], state="*")
    dp.register_message_handler(show_admin_panel, commands=["admin"])
    
    # Кнопка промокода
    dp.register_message_handler(
        show_promo_input,
        lambda m: m.text in ["🎁 Promo Code", "🎁 Промокод"],
        state="*"
    )
    
    # Обработка введённого промокода
    dp.register_message_handler(
        handle_promo_code,
        state=PromoStates.waiting_for_promo
    )
    
    # Текстовые кнопки
    dp.register_message_handler(
        show_alerts_menu,
        lambda m: m.text in ["📈 Alerts", "📈 Алерты"]
    )
    dp.register_message_handler(
        show_guide,
        lambda m: m.text in ["📖 Guide", "📖 Инструкция"]
    )
    dp.register_message_handler(
        show_support,
        lambda m: m.text in ["💬 Support", "💬 Поддержка"]
    )
    dp.register_message_handler(
        show_stats,
        lambda m: m.text in ["📊 Statistics", "📊 Статистика"]
    )
    
    # Кнопка "Открыть доступ" - показываем меню оплаты
    @dp.message_handler(lambda m: m.text in ["🔓 Get Access", "🔓 Открыть доступ"])
    async def open_access(message: types.Message):
        await show_payment_menu(message, is_callback=False)
    
    # Callback: выбор языка
    dp.register_callback_query_handler(
        handle_language_selection,
        lambda c: c.data.startswith("lang_")
    )
    
    # Callback кнопки
    dp.register_callback_query_handler(handle_callbacks, lambda c: True)
    
    # ==================== ПЛАТЁЖНЫЕ ОБРАБОТЧИКИ ====================
    
    # Меню оплаты
    @dp.callback_query_handler(lambda c: c.data == "menu_pay")
    async def menu_pay(call: types.CallbackQuery):
        await show_payment_menu(call, is_callback=True)
    
    # Выбор тарифного плана
    @dp.callback_query_handler(lambda c: c.data.startswith("pay_") and len(c.data.split("_")) == 2)
    async def select_plan(call: types.CallbackQuery):
        await handle_plan_selection(call)
    
    # Проверка оплаты
    @dp.callback_query_handler(lambda c: c.data.startswith("check_"))
    async def check_payment(call: types.CallbackQuery):
        await handle_payment_check(call)
    
    logger.info("All handlers registered successfully")
