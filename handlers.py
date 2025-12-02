"""
handlers.py - Полная интеграция всех обработчиков (ИСПРАВЛЕНО)
Включает: основные команды, платежи, PnL статистику
"""
import logging
from aiogram import Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_IDS, DEFAULT_PAIRS
from database import (
    add_user, user_exists, get_user_lang, set_user_lang,
    is_paid, grant_access, revoke_access, get_user_pairs,
    add_user_pair, remove_user_pair, get_total_users, get_paid_users_count
)

# Импорты для платежей
from payment_handlers import (
    show_payment_menu,
    handle_plan_selection,
    handle_payment_check
)

# Импорты для PnL
from pnl_handlers import (
    cmd_stats,
    cmd_active,
    stats_period_callback,
    stats_pairs_callback
)

logger = logging.getLogger(__name__)

# ==================== /start ====================
async def cmd_start(message: types.Message):
    """Команда /start"""
    user_id = message.from_user.id
    
    # Проверяем существование пользователя
    if not await user_exists(user_id):
        await add_user(user_id, "ru")
        await show_language_selection(message)
        return
    
    # Получаем язык
    lang = await get_user_lang(user_id)
    
    # Проверяем оплату
    paid = await is_paid(user_id)
    
    # Главное меню
    await show_main_menu(message, lang, paid)

async def show_language_selection(message: types.Message):
    """Выбор языка"""
    text = "🌍 <b>Choose your language / Выбери язык</b>\n\n"
    text += "Select your preferred language for the bot interface."
    
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
    )
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

async def show_main_menu(message: types.Message, lang: str, paid: bool):
    """Главное меню"""
    if lang == "en":
        if paid:
            text = "🎯 <b>Alpha Entry Bot</b>\n\n"
            text += "You have <b>PREMIUM ACCESS</b> ✅\n\n"
            text += "🔔 You'll receive 3-5 quality signals daily\n"
            text += "📊 Multi-strategy analysis\n"
            text += "🎯 Automatic TP/SL levels\n\n"
            text += "Choose an action:"
        else:
            text = "🎯 <b>Alpha Entry Bot</b>\n\n"
            text += "Professional crypto trading signals with 70%+ winrate\n\n"
            text += "🎯 <b>Features:</b>\n"
            text += "• 3-5 quality signals per day\n"
            text += "• Multi-strategy analysis\n"
            text += "• Automatic TP/SL levels\n"
            text += "• Up to 10 coins\n"
            text += "• 24/7 monitoring\n\n"
            text += "Get premium access to start earning! 💰"
    else:
        if paid:
            text = "🎯 <b>Alpha Entry Bot</b>\n\n"
            text += "У тебя <b>ПРЕМИУМ ДОСТУП</b> ✅\n\n"
            text += "🔔 Получай 3-5 качественных сигналов ежедневно\n"
            text += "📊 Мультистратегия анализа\n"
            text += "🎯 Автоматические уровни TP/SL\n\n"
            text += "Выбери действие:"
        else:
            text = "🎯 <b>Alpha Entry Bot</b>\n\n"
            text += "Профессиональные крипто сигналы с винрейтом 70%+\n\n"
            text += "🎯 <b>Возможности:</b>\n"
            text += "• 3-5 качественных сигналов в день\n"
            text += "• Мультистратегия анализа\n"
            text += "• Автоматические уровни TP/SL\n"
            text += "• До 10 монет\n"
            text += "• Мониторинг 24/7\n\n"
            text += "Получи премиум доступ и начни зарабатывать! 💰"
    
    # Кнопки
    kb = InlineKeyboardMarkup(row_width=2)
    
    if paid:
        # Меню для оплативших
        if lang == "en":
            kb.add(
                InlineKeyboardButton("📈 Alerts", callback_data="menu_alerts"),
                InlineKeyboardButton("📚 Guide", callback_data="menu_guide")
            )
            kb.add(
                InlineKeyboardButton("📊 Stats", callback_data="menu_stats"),
                InlineKeyboardButton("⏳ Active", callback_data="menu_active")
            )
            kb.add(
                InlineKeyboardButton("👥 Referral", callback_data="menu_ref"),
                InlineKeyboardButton("💬 Support", callback_data="menu_support")
            )
        else:
            kb.add(
                InlineKeyboardButton("📈 Алерты", callback_data="menu_alerts"),
                InlineKeyboardButton("📚 Инструкция", callback_data="menu_guide")
            )
            kb.add(
                InlineKeyboardButton("📊 Статистика", callback_data="menu_stats"),
                InlineKeyboardButton("⏳ Активные", callback_data="menu_active")
            )
            kb.add(
                InlineKeyboardButton("👥 Рефералка", callback_data="menu_ref"),
                InlineKeyboardButton("💬 Поддержка", callback_data="menu_support")
            )
    else:
        # Меню для неоплативших
        if lang == "en":
            kb.add(
                InlineKeyboardButton("👥 Referral", callback_data="menu_ref"),
                InlineKeyboardButton("🔓 Get Access", callback_data="menu_pay")
            )
            kb.add(
                InlineKeyboardButton("📚 Guide", callback_data="menu_guide"),
                InlineKeyboardButton("💬 Support", callback_data="menu_support")
            )
        else:
            kb.add(
                InlineKeyboardButton("👥 Рефералка", callback_data="menu_ref"),
                InlineKeyboardButton("🔓 Открыть доступ", callback_data="menu_pay")
            )
            kb.add(
                InlineKeyboardButton("📚 Инструкция", callback_data="menu_guide"),
                InlineKeyboardButton("💬 Поддержка", callback_data="menu_support")
            )
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# ==================== АДМИН ПАНЕЛЬ ====================
async def show_admin_panel(message: types.Message):
    """Админ панель"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await message.answer("❌ Access denied")
        return
    
    total = await get_total_users()
    paid = await get_paid_users_count()
    
    text = f"👨‍💼 <b>АДМИН ПАНЕЛЬ</b>\n\n"
    text += f"📊 Всего пользователей: {total}\n"
    text += f"💰 Оплативших: {paid}\n"
    text += f"📈 Conversion: {(paid/total*100) if total > 0 else 0:.1f}%\n"
    
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📤 Broadcast", callback_data="admin_broadcast"),
        InlineKeyboardButton("✅ Grant Access", callback_data="admin_grant")
    )
    kb.add(
        InlineKeyboardButton("❌ Revoke Access", callback_data="admin_revoke"),
        InlineKeyboardButton("🧪 Test Signal", callback_data="admin_test_signal")
    )
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

async def test_signal_command(message: types.Message):
    """Тестовый сигнал"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        return
    
    await message.answer("🔍 Генерирую тестовый сигнал...")
    
    from scheduler import send_test_signal
    await send_test_signal(message.bot, user_id)

# ==================== CALLBACK HANDLER ====================
async def handle_callbacks(call: types.CallbackQuery):
    """Обработчик всех callback"""
    data = call.data
    user_id = call.from_user.id
    lang = await get_user_lang(user_id)
    paid = await is_paid(user_id)
    
    # Выбор языка
    if data.startswith("lang_"):
        new_lang = data.split("_")[1]
        await set_user_lang(user_id, new_lang)
        await call.message.delete()
        await show_main_menu(call.message, new_lang, paid)
        await call.answer("✅ Language set!" if new_lang == "en" else "✅ Язык установлен!")
        return
    
    # Главное меню
    elif data == "back_main":
        await call.message.delete()
        await show_main_menu(call.message, lang, paid)
        await call.answer()
        return
    
    # Меню алертов
    elif data == "menu_alerts":
        if not paid:
            await call.answer("❌ Premium required", show_alert=True)
            return
        await show_alerts_menu(call)
        return
    
    # Статистика
    elif data == "menu_stats":
        if not paid:
            await call.answer("❌ Premium required", show_alert=True)
            return
        await cmd_stats(call.message)
        await call.answer()
        return
    
    # Активные сигналы
    elif data == "menu_active":
        if not paid:
            await call.answer("❌ Premium required", show_alert=True)
            return
        await cmd_active(call.message)
        await call.answer()
        return
    
    # Остальные меню
    elif data == "menu_guide":
        await show_guide(call)
        return
    
    elif data == "menu_support":
        await show_support(call)
        return
    
    elif data == "menu_ref":
        await show_referral(call)
        return
    
    # Админ команды
    elif data.startswith("admin_"):
        if user_id not in ADMIN_IDS:
            await call.answer("❌ Access denied", show_alert=True)
            return
        
        if data == "admin_test_signal":
            await call.message.answer("🔍 Генерирую тестовый сигнал...")
            from scheduler import send_test_signal
            await send_test_signal(call.message.bot, user_id)
            await call.answer()
        
        return
    
    await call.answer()

async def show_alerts_menu(call: types.CallbackQuery):
    """Меню управления алертами"""
    user_id = call.from_user.id
    lang = await get_user_lang(user_id)
    
    user_pairs = await get_user_pairs(user_id)
    
    if lang == "en":
        text = "📈 <b>ALERTS MANAGEMENT</b>\n\n"
        text += f"You're tracking <b>{len(user_pairs)}</b> pairs\n\n"
        if user_pairs:
            text += "Active pairs:\n"
            for pair in user_pairs:
                text += f"• {pair}\n"
        text += "\nSelect action:"
    else:
        text = "📈 <b>УПРАВЛЕНИЕ АЛЕРТАМИ</b>\n\n"
        text += f"Отслеживается пар: <b>{len(user_pairs)}</b>\n\n"
        if user_pairs:
            text += "Активные пары:\n"
            for pair in user_pairs:
                text += f"• {pair}\n"
        text += "\nВыбери действие:"
    
    kb = InlineKeyboardMarkup(row_width=2)
    
    if lang == "en":
        kb.add(
            InlineKeyboardButton("➕ Add Pair", callback_data="alerts_add"),
            InlineKeyboardButton("➖ Remove Pair", callback_data="alerts_remove")
        )
        kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back_main"))
    else:
        kb.add(
            InlineKeyboardButton("➕ Добавить пару", callback_data="alerts_add"),
            InlineKeyboardButton("➖ Удалить пару", callback_data="alerts_remove")
        )
        kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_main"))
    
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    
    await call.answer()

async def show_guide(call: types.CallbackQuery):
    """Показать инструкцию"""
    lang = await get_user_lang(call.from_user.id)
    
    if lang == "en":
        text = "📚 <b>USER GUIDE</b>\n\n"
        text += "<b>How to use signals:</b>\n\n"
        text += "1️⃣ Wait for signal notification\n"
        text += "2️⃣ Check the score (70+ recommended)\n"
        text += "3️⃣ Open position at entry price\n"
        text += "4️⃣ Set TP/SL as indicated\n"
        text += "5️⃣ Close portions at TP1/TP2/TP3\n\n"
        text += "<b>Risk Management:</b>\n"
        text += "• Never risk more than 2% per trade\n"
        text += "• Always use stop loss\n"
        text += "• Take partial profits at each TP\n\n"
        text += "⚠️ <i>Not financial advice</i>"
    else:
        text = "📚 <b>ИНСТРУКЦИЯ</b>\n\n"
        text += "<b>Как использовать сигналы:</b>\n\n"
        text += "1️⃣ Дождись уведомления о сигнале\n"
        text += "2️⃣ Проверь оценку (70+ рекомендуется)\n"
        text += "3️⃣ Открой позицию по цене входа\n"
        text += "4️⃣ Установи TP/SL как указано\n"
        text += "5️⃣ Закрывай частями на TP1/TP2/TP3\n\n"
        text += "<b>Управление рисками:</b>\n"
        text += "• Никогда не рискуй >2% на сделку\n"
        text += "• Всегда используй стоп-лосс\n"
        text += "• Фиксируй прибыль частями на каждом TP\n\n"
        text += "⚠️ <i>Не является финансовым советом</i>"
    
    kb = InlineKeyboardMarkup()
    back_text = "⬅️ Back" if lang == "en" else "⬅️ Назад"
    kb.add(InlineKeyboardButton(back_text, callback_data="back_main"))
    
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    
    await call.answer()

async def show_support(call: types.CallbackQuery):
    """Показать поддержку"""
    lang = await get_user_lang(call.from_user.id)
    
    if lang == "en":
        text = "💬 <b>SUPPORT</b>\n\n"
        text += "Have questions or issues?\n\n"
        text += "📧 Contact: @support\n"
        text += "📱 Community: @alphaentrychannel\n\n"
        text += "We're here to help! 24/7"
    else:
        text = "💬 <b>ПОДДЕРЖКА</b>\n\n"
        text += "Есть вопросы или проблемы?\n\n"
        text += "📧 Контакт: @support\n"
        text += "📱 Сообщество: @alphaentrychannel\n\n"
        text += "Мы здесь чтобы помочь! 24/7"
    
    kb = InlineKeyboardMarkup()
    back_text = "⬅️ Back" if lang == "en" else "⬅️ Назад"
    kb.add(InlineKeyboardButton(back_text, callback_data="back_main"))
    
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    
    await call.answer()

async def show_referral(call: types.CallbackQuery):
    """Показать реферальную систему"""
    user_id = call.from_user.id
    lang = await get_user_lang(user_id)
    
    ref_link = f"https://t.me/YOUR_BOT?start=ref{user_id}"
    
    if lang == "en":
        text = "👥 <b>REFERRAL PROGRAM</b>\n\n"
        text += "Invite friends and earn 20% from their payments!\n\n"
        text += f"Your referral link:\n<code>{ref_link}</code>\n\n"
        text += "<b>Your stats:</b>\n"
        text += "Referrals: 0\n"
        text += "Earned: $0.00\n\n"
        text += "💡 Share your link and start earning!"
    else:
        text = "👥 <b>РЕФЕРАЛЬНАЯ ПРОГРАММА</b>\n\n"
        text += "Приглашай друзей и получай 20% от их платежей!\n\n"
        text += f"Твоя реферальная ссылка:\n<code>{ref_link}</code>\n\n"
        text += "<b>Твоя статистика:</b>\n"
        text += "Рефералов: 0\n"
        text += "Заработано: $0.00\n\n"
        text += "💡 Делись ссылкой и начинай зарабатывать!"
    
    kb = InlineKeyboardMarkup()
    back_text = "⬅️ Back" if lang == "en" else "⬅️ Назад"
    kb.add(InlineKeyboardButton(back_text, callback_data="back_main"))
    
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    
    await call.answer()

# ==================== SETUP ====================
def setup_handlers(dp: Dispatcher):
    """Регистрация всех обработчиков"""
    
    # Основные команды
    dp.register_message_handler(cmd_start, commands=["start"], state="*")
    dp.register_message_handler(show_admin_panel, commands=["admin"])
    dp.register_message_handler(test_signal_command, commands=["test_signal"])
    
    # PnL команды
    dp.register_message_handler(cmd_stats, commands=["stats"])
    dp.register_message_handler(cmd_active, commands=["active"])
    
    # Платёжные callbacks
    dp.register_callback_query_handler(
        lambda c: show_payment_menu(c, is_callback=True),
        lambda c: c.data == "menu_pay"
    )
    dp.register_callback_query_handler(
        handle_plan_selection,
        lambda c: c.data.startswith("pay_") and len(c.data.split("_")) == 2
    )
    dp.register_callback_query_handler(
        handle_payment_check,
        lambda c: c.data.startswith("check_")
    )
    
    # PnL callbacks
    dp.register_callback_query_handler(
        stats_period_callback,
        lambda c: c.data.startswith("stats_") and c.data.split("_")[1].isdigit()
    )
    dp.register_callback_query_handler(
        stats_pairs_callback,
        lambda c: c.data == "stats_pairs"
    )
    
    # Общий обработчик callbacks
    dp.register_callback_query_handler(handle_callbacks, lambda c: True)
    
    logger.info("✅ All handlers registered")
