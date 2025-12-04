"""
handlers.py - Полная интеграция всех обработчиков (С ПРОМОКОДАМИ И КАРТИНКАМИ)
Включает: основные команды, платежи, PnL статистику, промокоды
"""
import logging
from aiogram import Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

from config import ADMIN_IDS, DEFAULT_PAIRS, IMG_START, IMG_ALERTS, IMG_REF, IMG_PAYWALL, IMG_GUIDE
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

# ==================== ПРОМОКОДЫ ====================
PROMO_CODES = {
    "AbramDanke123": {
        "type": "full_access",
        "days": 9999,  # Практически навсегда
        "uses": 999,    # Много использований
        "description": "Abram's personal promo code"
    }
}

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
    
    # Убираем старые кнопки внизу
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
            text += "💡 <b>Have a promo code?</b> Just send it!\n\n"
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
            text += "💡 <b>Есть промокод?</b> Просто отправь его!\n\n"
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
    
    # Отправляем с картинкой если есть
    if IMG_START:
        try:
            await message.answer_photo(IMG_START, caption=text, reply_markup=kb, parse_mode="HTML")
        except:
            # Если картинка не работает, отправляем просто текст
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

# ==================== ОБРАБОТКА ПРОМОКОДОВ ====================
async def handle_promo_code(message: types.Message):
    """Обработка промокодов"""
    user_id = message.from_user.id
    promo_code = message.text.strip()
    lang = await get_user_lang(user_id)
    
    # Проверяем есть ли такой промокод
    if promo_code not in PROMO_CODES:
        # Не промокод, игнорируем
        return
    
    # Проверяем не оплачен ли уже
    if await is_paid(user_id):
        if lang == "en":
            text = "⚠️ You already have premium access!"
        else:
            text = "⚠️ У тебя уже есть премиум доступ!"
        await message.answer(text)
        return
    
    promo_info = PROMO_CODES[promo_code]
    
    # Выдаём доступ
    await grant_access(user_id)
    
    logger.info(f"User {user_id} activated promo code: {promo_code}")
    
    # Уведомление
    if lang == "en":
        text = f"🎉 <b>SUCCESS!</b>\n\n"
        text += f"Promo code <code>{promo_code}</code> activated!\n\n"
        text += f"✅ Premium access granted!\n"
        text += f"📊 You'll receive 3-5 quality signals daily\n"
        text += f"🎯 Automatic TP/SL levels\n\n"
        text += f"Use /start to see main menu"
    else:
        text = f"🎉 <b>УСПЕХ!</b>\n\n"
        text += f"Промокод <code>{promo_code}</code> активирован!\n\n"
        text += f"✅ Премиум доступ выдан!\n"
        text += f"📊 Получай 3-5 качественных сигналов ежедневно\n"
        text += f"🎯 Автоматические уровни TP/SL\n\n"
        text += f"Используй /start чтобы открыть главное меню"
    
    await message.answer(text, parse_mode="HTML")

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
        InlineKeyboardButton("📊 Stats", callback_data="admin_stats")
    )
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# ==================== CALLBACK ОБРАБОТЧИКИ ====================
async def handle_callbacks(call: types.CallbackQuery):
    """Обработка всех callback кнопок"""
    user_id = call.from_user.id
    data = call.data
    lang = await get_user_lang(user_id)
    
    # Язык
    if data.startswith("lang_"):
        new_lang = data.split("_")[1]
        await set_user_lang(user_id, new_lang)
        
        if new_lang == "en":
            text = "✅ Language changed to English"
        else:
            text = "✅ Язык изменён на русский"
        
        await call.answer(text)
        await call.message.delete()
        await show_main_menu(call.message, new_lang, await is_paid(user_id))
        return
    
    # Главное меню
    if data == "back_main":
        paid = await is_paid(user_id)
        await show_main_menu(call.message, lang, paid)
        await call.answer()
        return
    
    # Алерты
    if data == "menu_alerts":
        await show_alerts_menu(call.message, lang)
        await call.answer()
        return
    
    # Инструкция
    if data == "menu_guide":
        await show_guide(call.message, lang)
        await call.answer()
        return
    
    # Статистика
    if data == "menu_stats":
        await cmd_stats(call.message)
        await call.answer()
        return
    
    # Активные сигналы
    if data == "menu_active":
        await cmd_active(call.message)
        await call.answer()
        return
    
    # Рефералка
    if data == "menu_ref":
        await show_referral(call.message, lang)
        await call.answer()
        return
    
    # Поддержка
    if data == "menu_support":
        await show_support(call.message, lang)
        await call.answer()
        return
    
    # Управление монетами
    if data == "manage_coins":
        await show_manage_coins(call.message, lang)
        await call.answer()
        return
    
    # Включить монету
    if data.startswith("coin_on_"):
        pair = data.replace("coin_on_", "")
        await add_user_pair(user_id, pair)
        await show_manage_coins(call.message, lang)
        await call.answer(f"✅ {pair} включён!" if lang == "ru" else f"✅ {pair} enabled!")
        return
    
    # Выключить монету
    if data.startswith("coin_off_"):
        pair = data.replace("coin_off_", "")
        await remove_user_pair(user_id, pair)
        await show_manage_coins(call.message, lang)
        await call.answer(f"❌ {pair} выключен!" if lang == "ru" else f"❌ {pair} disabled!")
        return
    
    # Включить все монеты
    if data == "coins_all_on":
        for pair in DEFAULT_PAIRS:
            await add_user_pair(user_id, pair)
        await show_manage_coins(call.message, lang)
        await call.answer("✅ Все монеты включены!" if lang == "ru" else "✅ All coins enabled!", show_alert=True)
        return
    
    # Выключить все монеты
    if data == "coins_all_off":
        for pair in DEFAULT_PAIRS:
            await remove_user_pair(user_id, pair)
        await show_manage_coins(call.message, lang)
        await call.answer("❌ Все монеты выключены!" if lang == "ru" else "❌ All coins disabled!", show_alert=True)
        return
    
    await call.answer()

# ==================== МЕНЮ РАЗДЕЛОВ ====================
async def show_alerts_menu(message: types.Message, lang: str):
    """Меню алертов - УЛУЧШЕННОЕ ОТОБРАЖЕНИЕ"""
    pairs = await get_user_pairs(message.from_user.id)
    
    if lang == "en":
        text = "📈 <b>ALERTS SETTINGS</b>\n\n"
        
        if pairs:
            text += f"✅ <b>Active coins ({len(pairs)}/{len(DEFAULT_PAIRS)}):</b>\n"
            # Показываем монеты в строку
            pairs_display = ", ".join([p.replace("USDT", "") for p in pairs])
            text += f"<code>{pairs_display}</code>\n\n"
            text += "💡 Signals are sent automatically when conditions are met"
        else:
            text += "⚠️ <b>No coins enabled!</b>\n\n"
            text += "You won't receive any signals.\n"
            text += "👇 Click «Manage Coins» to enable coins"
    else:
        text = "📈 <b>НАСТРОЙКИ АЛЕРТОВ</b>\n\n"
        
        if pairs:
            text += f"✅ <b>Активные монеты ({len(pairs)}/{len(DEFAULT_PAIRS)}):</b>\n"
            # Показываем монеты в строку
            pairs_display = ", ".join([p.replace("USDT", "") for p in pairs])
            text += f"<code>{pairs_display}</code>\n\n"
            text += "💡 Сигналы отправляются автоматически при выполнении условий"
        else:
            text += "⚠️ <b>Нет активных монет!</b>\n\n"
            text += "Ты не будешь получать сигналы.\n"
            text += "👇 Нажми «Настроить монеты» чтобы включить"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⚙️ Настроить монеты" if lang == "ru" else "⚙️ Manage Coins", callback_data="manage_coins"))
    kb.add(InlineKeyboardButton("⬅️ Назад" if lang == "ru" else "⬅️ Back", callback_data="back_main"))
    
    # С картинкой если есть
    if IMG_ALERTS:
        try:
            await message.edit_media(
                media=types.InputMediaPhoto(IMG_ALERTS, caption=text, parse_mode="HTML"),
                reply_markup=kb
            )
            return
        except:
            pass
    
    try:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

async def show_manage_coins(message: types.Message, lang: str):
    """Управление монетами - УЛУЧШЕННОЕ ОТОБРАЖЕНИЕ"""
    user_id = message.from_user.id
    user_pairs = await get_user_pairs(user_id)
    
    if lang == "en":
        text = "⚙️ <b>MANAGE COINS</b>\n\n"
        
        # Показываем активные монеты вверху
        if user_pairs:
            text += f"✅ <b>Active ({len(user_pairs)}):</b> "
            text += ", ".join([p.replace("USDT", "") for p in user_pairs])
            text += "\n\n"
        else:
            text += "⚠️ <b>No coins active</b>\n\n"
        
        text += "Tap coin to toggle ON/OFF:"
    else:
        text = "⚙️ <b>НАСТРОЙКА МОНЕТ</b>\n\n"
        
        # Показываем активные монеты вверху
        if user_pairs:
            text += f"✅ <b>Активные ({len(user_pairs)}):</b> "
            text += ", ".join([p.replace("USDT", "") for p in user_pairs])
            text += "\n\n"
        else:
            text += "⚠️ <b>Нет активных монет</b>\n\n"
        
        text += "Нажми на монету чтобы вкл/выкл:"
    
    # Кнопки с монетами (3 в ряд)
    kb = InlineKeyboardMarkup(row_width=3)
    
    buttons = []
    for pair in DEFAULT_PAIRS:
        # Галочка если монета включена
        if pair in user_pairs:
            emoji = "✅"
            callback = f"coin_off_{pair}"
        else:
            emoji = "⬜"
            callback = f"coin_on_{pair}"
        
        buttons.append(InlineKeyboardButton(
            f"{emoji} {pair.replace('USDT', '')}",
            callback_data=callback
        ))
    
    # Добавляем по 3 кнопки в ряд
    for i in range(0, len(buttons), 3):
        kb.row(*buttons[i:i+3])
    
    # Кнопки управления
    kb.row(
        InlineKeyboardButton("✅ Все ВКЛ" if lang == "ru" else "✅ All ON", callback_data="coins_all_on"),
        InlineKeyboardButton("⬜ Все ВЫКЛ" if lang == "ru" else "⬜ All OFF", callback_data="coins_all_off")
    )
    kb.add(InlineKeyboardButton("⬅️ Назад" if lang == "ru" else "⬅️ Back", callback_data="menu_alerts"))
    
    try:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

async def show_guide(message: types.Message, lang: str):
    """Инструкция"""
    if lang == "en":
        text = "📚 <b>HOW TO USE</b>\n\n"
        text += "1️⃣ <b>Receive Signal</b>\n"
        text += "You'll get 3-5 signals daily with entry points and TP/SL levels\n\n"
        text += "2️⃣ <b>Open Position</b>\n"
        text += "Enter at the specified price\n\n"
        text += "3️⃣ <b>Take Profits</b>\n"
        text += "• TP1 - close 15% of position\n"
        text += "• TP2 - close 40% of position\n"
        text += "• TP3 - close 80% of position\n\n"
        text += "4️⃣ <b>Stop Loss</b>\n"
        text += "Always set SL to protect your capital\n\n"
        text += "💡 Average signal accuracy: 70%+"
    else:
        text = "📚 <b>КАК ИСПОЛЬЗОВАТЬ</b>\n\n"
        text += "1️⃣ <b>Получи сигнал</b>\n"
        text += "Ты будешь получать 3-5 сигналов в день с точками входа и TP/SL\n\n"
        text += "2️⃣ <b>Открой позицию</b>\n"
        text += "Войди по указанной цене\n\n"
        text += "3️⃣ <b>Забирай профит</b>\n"
        text += "• TP1 - закрой 15% позиции\n"
        text += "• TP2 - закрой 40% позиции\n"
        text += "• TP3 - закрой 80% позиции\n\n"
        text += "4️⃣ <b>Стоп лосс</b>\n"
        text += "Всегда ставь SL для защиты капитала\n\n"
        text += "💡 Средняя точность сигналов: 70%+"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Назад" if lang == "ru" else "⬅️ Back", callback_data="back_main"))
    
    # С картинкой если есть
    if IMG_GUIDE:
        try:
            await message.edit_media(
                media=types.InputMediaPhoto(IMG_GUIDE, caption=text, parse_mode="HTML"),
                reply_markup=kb
            )
            return
        except:
            pass
    
    try:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

async def show_referral(message: types.Message, lang: str):
    """Реферальная программа"""
    user_id = message.from_user.id
    ref_link = f"https://t.me/{(await message.bot.get_me()).username}?start=ref{user_id}"
    
    if lang == "en":
        text = "👥 <b>REFERRAL PROGRAM</b>\n\n"
        text += "Invite friends and get <b>10% commission</b> from their payments!\n\n"
        text += f"Your referral link:\n<code>{ref_link}</code>\n\n"
        text += "💰 Your earnings: $0.00\n"
        text += "👥 Referred users: 0"
    else:
        text = "👥 <b>РЕФЕРАЛЬНАЯ ПРОГРАММА</b>\n\n"
        text += "Приглашай друзей и получай <b>10% комиссию</b> с их платежей!\n\n"
        text += f"Твоя реферальная ссылка:\n<code>{ref_link}</code>\n\n"
        text += "💰 Твой заработок: $0.00\n"
        text += "👥 Приглашено пользователей: 0"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Назад" if lang == "ru" else "⬅️ Back", callback_data="back_main"))
    
    # С картинкой если есть
    if IMG_REF:
        try:
            await message.edit_media(
                media=types.InputMediaPhoto(IMG_REF, caption=text, parse_mode="HTML"),
                reply_markup=kb
            )
            return
        except:
            pass
    
    try:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

async def show_support(message: types.Message, lang: str):
    """Поддержка"""
    if lang == "en":
        text = "💬 <b>SUPPORT</b>\n\n"
        text += "Got questions or issues?\n\n"
        text += "📧 Contact: @support\n"
        text += "⏰ Response time: up to 24 hours"
    else:
        text = "💬 <b>ПОДДЕРЖКА</b>\n\n"
        text += "Есть вопросы или проблемы?\n\n"
        text += "📧 Контакт: @support\n"
        text += "⏰ Время ответа: до 24 часов"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Назад" if lang == "ru" else "⬅️ Back", callback_data="back_main"))
    
    try:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

# ==================== ТЕСТОВЫЙ СИГНАЛ ====================
async def test_signal_command(message: types.Message):
    """Тестовый сигнал (только для админов)"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    text = "📈 <b>СИГНАЛ (85/100)</b>\n\n"
    text += "<b>Монета:</b> BTCUSDT\n"
    text += "<b>Вход:</b> LONG @ 42,350.00\n\n"
    text += "🎯 <b>TP1:</b> 42,650 (+0.71%) [15% позиции]\n"
    text += "🎯 <b>TP2:</b> 43,250 (+2.12%) [40% позиции]\n"
    text += "🎯 <b>TP3:</b> 44,350 (+4.72%) [80% позиции]\n\n"
    text += "🛡 <b>SL:</b> 41,950 (-0.94%)\n\n"
    text += "💡 <b>Причины:</b>\n"
    text += "• ✅ Восходящий тренд (EMA 9>21>50)\n"
    text += "• 🎯 RSI идеален (52.3)\n"
    text += "• ✅ MACD бычий\n"
    text += "• 🔥 Очень высокий объём (2.3x)\n"
    text += "• ⚡ Очень сильный импульс\n\n"
    text += "⏰ 21:30:00"
    
    await message.answer(text, parse_mode="HTML")

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
    
    # Обработка промокодов (ВАЖНО - до общего обработчика текста!)
    dp.register_message_handler(handle_promo_code, content_types=["text"], state="*")
    
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
    
    logger.info("✅ All handlers registered (including promo codes)")
