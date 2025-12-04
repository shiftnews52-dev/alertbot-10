"""
handlers.py - ПОЛНАЯ ВЕРСИЯ
- Картинки (IMG_START, IMG_ALERTS, IMG_REF, IMG_GUIDE)
- Промокод AbramDanke123
- Выбор языка
- Удаление сообщений при переходе
- Убрана статистика
- Админ панель
"""
import logging
from aiogram import Dispatcher, Bot, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_IDS, DEFAULT_PAIRS, IMG_START, IMG_ALERTS, IMG_REF, IMG_PAYWALL, IMG_GUIDE
from database import (
    add_user, user_exists, get_user_lang, set_user_lang,
    is_paid, grant_access, revoke_access, get_user_pairs,
    add_user_pair, remove_user_pair, get_total_users, get_paid_users_count,
    get_all_users
)

# Импорты для платежей
from payment_handlers import (
    show_payment_menu,
    handle_plan_selection,
    handle_payment_check
)

logger = logging.getLogger(__name__)

# ==================== ПРОМОКОДЫ ====================
PROMO_CODES = {
    "AbramDanke123": {
        "type": "full_access",
        "days": 9999,
        "uses": 999,
        "description": "Abram's personal promo code"
    },
    "abramdanke123": {
        "type": "full_access",
        "days": 9999,
        "uses": 999,
        "description": "Abram's personal promo code (lowercase)"
    },
    "ABRAMDANKE123": {
        "type": "full_access",
        "days": 9999,
        "uses": 999,
        "description": "Abram's personal promo code (uppercase)"
    }
}

# Состояние для рассылки
broadcast_state = {}


# ==================== ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ====================
async def delete_and_send(message: types.Message, text: str, kb: InlineKeyboardMarkup, photo: str = None):
    """Удалить старое сообщение и отправить новое"""
    chat_id = message.chat.id
    
    try:
        await message.delete()
    except:
        pass
    
    bot = Bot.get_current()
    
    if photo:
        try:
            await bot.send_photo(chat_id, photo, caption=text, reply_markup=kb, parse_mode="HTML")
            return
        except:
            pass
    
    await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")


# ==================== /start ====================
async def cmd_start(message: types.Message):
    """Команда /start"""
    user_id = message.from_user.id
    
    # Новый пользователь - показываем выбор языка
    if not await user_exists(user_id):
        await add_user(user_id, "ru")
        await show_language_selection(message)
        return
    
    lang = await get_user_lang(user_id)
    paid = await is_paid(user_id)
    
    await show_main_menu(message, lang, paid, is_start=True)


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


async def show_main_menu(message: types.Message, lang: str, paid: bool, is_start: bool = False):
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
    
    kb = InlineKeyboardMarkup(row_width=2)
    
    if paid:
        if lang == "en":
            kb.add(
                InlineKeyboardButton("📈 My Coins", callback_data="menu_coins"),
                InlineKeyboardButton("📚 Guide", callback_data="menu_guide")
            )
            kb.add(
                InlineKeyboardButton("👥 Referral", callback_data="menu_ref"),
                InlineKeyboardButton("💬 Support", callback_data="menu_support")
            )
        else:
            kb.add(
                InlineKeyboardButton("📈 Мои монеты", callback_data="menu_coins"),
                InlineKeyboardButton("📚 Инструкция", callback_data="menu_guide")
            )
            kb.add(
                InlineKeyboardButton("👥 Рефералка", callback_data="menu_ref"),
                InlineKeyboardButton("💬 Поддержка", callback_data="menu_support")
            )
    else:
        if lang == "en":
            kb.add(
                InlineKeyboardButton("🔓 Get Access", callback_data="menu_pay"),
                InlineKeyboardButton("📚 Guide", callback_data="menu_guide")
            )
            kb.add(
                InlineKeyboardButton("👥 Referral", callback_data="menu_ref"),
                InlineKeyboardButton("💬 Support", callback_data="menu_support")
            )
        else:
            kb.add(
                InlineKeyboardButton("🔓 Получить доступ", callback_data="menu_pay"),
                InlineKeyboardButton("📚 Инструкция", callback_data="menu_guide")
            )
            kb.add(
                InlineKeyboardButton("👥 Рефералка", callback_data="menu_ref"),
                InlineKeyboardButton("💬 Поддержка", callback_data="menu_support")
            )
    
    if is_start:
        # Первый запуск - отправляем новое сообщение
        if IMG_START:
            try:
                await message.answer_photo(IMG_START, caption=text, reply_markup=kb, parse_mode="HTML")
                return
            except:
                pass
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        # Переход из другого меню - удаляем старое
        await delete_and_send(message, text, kb, IMG_START)


# ==================== ПРОМОКОДЫ ====================
async def handle_promo_code(message: types.Message) -> bool:
    """Обработка промокода"""
    user_id = message.from_user.id
    
    # Если пользователя нет в базе - создаём
    if not await user_exists(user_id):
        await add_user(user_id, "ru")
    
    lang = await get_user_lang(user_id)
    code = message.text.strip()
    
    # Проверяем промокод (без учёта регистра)
    promo = None
    promo_key = None
    
    for key, value in PROMO_CODES.items():
        if code.lower() == key.lower():
            promo = value
            promo_key = key
            break
    
    if promo and promo["uses"] > 0:
        await grant_access(user_id, promo["days"])
        PROMO_CODES[promo_key]["uses"] -= 1
        
        if lang == "en":
            text = "🎉 <b>PROMO CODE ACTIVATED!</b>\n\n"
            text += f"✅ You now have premium access!\n"
            text += f"📅 Duration: {promo['days']} days\n\n"
            text += "Enjoy quality trading signals! 🚀"
        else:
            text = "🎉 <b>ПРОМОКОД АКТИВИРОВАН!</b>\n\n"
            text += f"✅ Теперь у тебя премиум доступ!\n"
            text += f"📅 Длительность: {promo['days']} дней\n\n"
            text += "Наслаждайся качественными сигналами! 🚀"
        
        await message.answer(text, parse_mode="HTML")
        await show_main_menu(message, lang, True, is_start=True)
        return True
    
    return False


# ==================== CALLBACK ОБРАБОТЧИКИ ====================
async def handle_callbacks(call: types.CallbackQuery):
    """Обработка callback кнопок"""
    user_id = call.from_user.id
    data = call.data
    lang = await get_user_lang(user_id)
    paid = await is_paid(user_id)
    
    await call.answer()
    
    # ===== ВЫБОР ЯЗЫКА =====
    if data.startswith("lang_"):
        new_lang = data.split("_")[1]
        await set_user_lang(user_id, new_lang)
        
        if new_lang == "en":
            await call.answer("✅ Language changed to English", show_alert=True)
        else:
            await call.answer("✅ Язык изменён на русский", show_alert=True)
        
        try:
            await call.message.delete()
        except:
            pass
        
        await show_main_menu(call.message, new_lang, paid, is_start=True)
        return
    
    # ===== ГЛАВНОЕ МЕНЮ =====
    if data == "back_main":
        await show_main_menu(call.message, lang, paid)
        return
    
    # ===== МОИ МОНЕТЫ =====
    if data == "menu_coins":
        await show_coins_menu(call.message, lang)
        return
    
    # ===== ИНСТРУКЦИЯ =====
    if data == "menu_guide":
        await show_guide(call.message, lang)
        return
    
    # ===== РЕФЕРАЛКА =====
    if data == "menu_ref":
        await show_referral(call.message, lang, user_id)
        return
    
    # ===== ПОДДЕРЖКА =====
    if data == "menu_support":
        await show_support(call.message, lang)
        return
    
    # ===== ОПЛАТА =====
    if data == "menu_pay":
        await show_payment_menu(call.message, lang)
        return
    
    # ===== МОНЕТЫ ВКЛ/ВЫКЛ =====
    if data.startswith("coin_on_"):
        pair = data.replace("coin_on_", "")
        await add_user_pair(user_id, pair)
        await show_coins_menu(call.message, lang)
        return
    
    if data.startswith("coin_off_"):
        pair = data.replace("coin_off_", "")
        await remove_user_pair(user_id, pair)
        await show_coins_menu(call.message, lang)
        return
    
    if data == "coins_all_on":
        for pair in DEFAULT_PAIRS:
            await add_user_pair(user_id, pair)
        await show_coins_menu(call.message, lang)
        return
    
    if data == "coins_all_off":
        for pair in DEFAULT_PAIRS:
            await remove_user_pair(user_id, pair)
        await show_coins_menu(call.message, lang)
        return
    
    # ===== ПЛАТЕЖИ =====
    if data.startswith("plan_"):
        await handle_plan_selection(call)
        return
    
    if data.startswith("check_"):
        await handle_payment_check(call)
        return
    
    # ===== АДМИН =====
    if data == "admin_refresh":
        if user_id in ADMIN_IDS:
            await show_admin_panel(call.message, is_callback=True)
        return
    
    if data == "admin_broadcast":
        if user_id in ADMIN_IDS:
            broadcast_state[user_id] = "waiting_message"
            text = "📤 <b>РАССЫЛКА</b>\n\nОтправь сообщение для рассылки.\n\nДля отмены: /cancel"
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("❌ Отмена", callback_data="admin_cancel"))
            await delete_and_send(call.message, text, kb)
        return
    
    if data == "admin_grant":
        if user_id in ADMIN_IDS:
            text = "✅ <b>ВЫДАТЬ ДОСТУП</b>\n\nОтправь команду:\n<code>/grant USER_ID DAYS</code>\n\nПример:\n<code>/grant 123456789 30</code>"
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="admin_back"))
            await delete_and_send(call.message, text, kb)
        return
    
    if data == "admin_revoke":
        if user_id in ADMIN_IDS:
            text = "❌ <b>ЗАБРАТЬ ДОСТУП</b>\n\nОтправь команду:\n<code>/revoke USER_ID</code>\n\nПример:\n<code>/revoke 123456789</code>"
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="admin_back"))
            await delete_and_send(call.message, text, kb)
        return
    
    if data == "admin_back":
        if user_id in ADMIN_IDS:
            await show_admin_panel(call.message, is_callback=True)
        return
    
    if data == "admin_cancel":
        if user_id in ADMIN_IDS:
            broadcast_state.pop(user_id, None)
            await show_admin_panel(call.message, is_callback=True)
        return
    
    if data == "admin_confirm_broadcast":
        if user_id in ADMIN_IDS and user_id in broadcast_state:
            msg_text = broadcast_state.get(f"{user_id}_text", "")
            if msg_text:
                await do_broadcast(call.message, msg_text)
                broadcast_state.pop(user_id, None)
                broadcast_state.pop(f"{user_id}_text", None)
        return


# ==================== МОИ МОНЕТЫ ====================
async def show_coins_menu(message: types.Message, lang: str):
    """Меню управления монетами"""
    user_id = message.chat.id
    user_pairs = await get_user_pairs(user_id)
    
    if lang == "en":
        text = "📈 <b>MY COINS</b>\n\n"
        if user_pairs:
            text += f"✅ Active: {len(user_pairs)}/{len(DEFAULT_PAIRS)}\n"
            coins = ", ".join([p.replace("USDT", "") for p in user_pairs])
            text += f"<code>{coins}</code>\n\n"
        else:
            text += "⚠️ No coins selected\n\n"
        text += "Tap to toggle:"
    else:
        text = "📈 <b>МОИ МОНЕТЫ</b>\n\n"
        if user_pairs:
            text += f"✅ Активных: {len(user_pairs)}/{len(DEFAULT_PAIRS)}\n"
            coins = ", ".join([p.replace("USDT", "") for p in user_pairs])
            text += f"<code>{coins}</code>\n\n"
        else:
            text += "⚠️ Монеты не выбраны\n\n"
        text += "Нажми чтобы вкл/выкл:"
    
    kb = InlineKeyboardMarkup(row_width=3)
    
    buttons = []
    for pair in DEFAULT_PAIRS:
        name = pair.replace("USDT", "")
        if pair in user_pairs:
            buttons.append(InlineKeyboardButton(f"✅ {name}", callback_data=f"coin_off_{pair}"))
        else:
            buttons.append(InlineKeyboardButton(f"⬜ {name}", callback_data=f"coin_on_{pair}"))
    
    for i in range(0, len(buttons), 3):
        kb.row(*buttons[i:i+3])
    
    if lang == "en":
        kb.row(
            InlineKeyboardButton("✅ All ON", callback_data="coins_all_on"),
            InlineKeyboardButton("⬜ All OFF", callback_data="coins_all_off")
        )
        kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back_main"))
    else:
        kb.row(
            InlineKeyboardButton("✅ Все ВКЛ", callback_data="coins_all_on"),
            InlineKeyboardButton("⬜ Все ВЫКЛ", callback_data="coins_all_off")
        )
        kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_main"))
    
    await delete_and_send(message, text, kb, IMG_ALERTS)


# ==================== ИНСТРУКЦИЯ ====================
async def show_guide(message: types.Message, lang: str):
    """Инструкция"""
    if lang == "en":
        text = "📚 <b>HOW TO USE</b>\n\n"
        text += "1️⃣ <b>Select coins</b>\n"
        text += "Go to 'My Coins' and enable coins you want to track\n\n"
        text += "2️⃣ <b>Wait for signals</b>\n"
        text += "Bot analyzes market 24/7 and sends quality signals\n\n"
        text += "3️⃣ <b>Open position</b>\n"
        text += "Enter at the specified price range\n\n"
        text += "4️⃣ <b>Take profits</b>\n"
        text += "• TP1 - close 30% of position\n"
        text += "• TP2 - close 40% of position\n"
        text += "• TP3 - close remaining 30%\n\n"
        text += "⚠️ <b>Always use stop-loss!</b>"
    else:
        text = "📚 <b>КАК ИСПОЛЬЗОВАТЬ</b>\n\n"
        text += "1️⃣ <b>Выбери монеты</b>\n"
        text += "Зайди в 'Мои монеты' и включи нужные монеты\n\n"
        text += "2️⃣ <b>Жди сигналы</b>\n"
        text += "Бот анализирует рынок 24/7 и отправляет качественные сигналы\n\n"
        text += "3️⃣ <b>Открой позицию</b>\n"
        text += "Входи по указанной цене\n\n"
        text += "4️⃣ <b>Фиксируй прибыль</b>\n"
        text += "• TP1 - закрыть 30% позиции\n"
        text += "• TP2 - закрыть 40% позиции\n"
        text += "• TP3 - закрыть оставшиеся 30%\n\n"
        text += "⚠️ <b>Всегда ставь стоп-лосс!</b>"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Назад" if lang == "ru" else "⬅️ Back", callback_data="back_main"))
    
    await delete_and_send(message, text, kb, IMG_GUIDE)


# ==================== РЕФЕРАЛКА ====================
async def show_referral(message: types.Message, lang: str, user_id: int):
    """Реферальная программа"""
    bot = Bot.get_current()
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    
    ref_link = f"https://t.me/{bot_username}?start=ref{user_id}"
    
    if lang == "en":
        text = "👥 <b>REFERRAL PROGRAM</b>\n\n"
        text += "Invite friends and get bonuses!\n\n"
        text += f"🔗 <b>Your link:</b>\n<code>{ref_link}</code>\n\n"
        text += "📋 Tap to copy"
    else:
        text = "👥 <b>РЕФЕРАЛЬНАЯ ПРОГРАММА</b>\n\n"
        text += "Приглашай друзей и получай бонусы!\n\n"
        text += f"🔗 <b>Твоя ссылка:</b>\n<code>{ref_link}</code>\n\n"
        text += "📋 Нажми чтобы скопировать"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Назад" if lang == "ru" else "⬅️ Back", callback_data="back_main"))
    
    await delete_and_send(message, text, kb, IMG_REF)


# ==================== ПОДДЕРЖКА ====================
async def show_support(message: types.Message, lang: str):
    """Поддержка"""
    if lang == "en":
        text = "💬 <b>SUPPORT</b>\n\n"
        text += "Have questions or problems?\n\n"
        text += "📩 Write to: @your_support"
    else:
        text = "💬 <b>ПОДДЕРЖКА</b>\n\n"
        text += "Есть вопросы или проблемы?\n\n"
        text += "📩 Пиши: @your_support"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Назад" if lang == "ru" else "⬅️ Back", callback_data="back_main"))
    
    await delete_and_send(message, text, kb)


# ==================== АДМИН ПАНЕЛЬ ====================
async def cmd_admin(message: types.Message):
    """Команда /admin"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    await show_admin_panel(message)


async def show_admin_panel(message: types.Message, is_callback: bool = False):
    """Показать админ панель"""
    total = await get_total_users()
    paid = await get_paid_users_count()
    conversion = (paid / total * 100) if total > 0 else 0
    
    text = "👨‍💼 <b>АДМИН ПАНЕЛЬ</b>\n\n"
    text += f"👥 Всего пользователей: <b>{total}</b>\n"
    text += f"💎 Премиум: <b>{paid}</b>\n"
    text += f"📈 Конверсия: <b>{conversion:.1f}%</b>\n\n"
    text += "<b>Команды:</b>\n"
    text += "/grant ID DAYS — выдать доступ\n"
    text += "/revoke ID — забрать доступ\n"
    text += "/broadcast — рассылка"
    
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📤 Рассылка", callback_data="admin_broadcast"),
        InlineKeyboardButton("✅ Выдать", callback_data="admin_grant")
    )
    kb.add(
        InlineKeyboardButton("❌ Забрать", callback_data="admin_revoke"),
        InlineKeyboardButton("🔄 Обновить", callback_data="admin_refresh")
    )
    
    if is_callback:
        await delete_and_send(message, text, kb)
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


async def cmd_grant(message: types.Message):
    """Выдать доступ: /grant USER_ID DAYS"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        parts = message.text.split()
        if len(parts) >= 2:
            target_id = int(parts[1])
            days = int(parts[2]) if len(parts) >= 3 else 30
            await grant_access(target_id, days)
            await message.answer(f"✅ Доступ выдан!\n\nUser ID: {target_id}\nДней: {days}")
        else:
            await message.answer("❌ Формат: /grant USER_ID [DAYS]\n\nПример: /grant 123456789 30")
    except ValueError:
        await message.answer("❌ Неверный ID пользователя")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


async def cmd_revoke(message: types.Message):
    """Забрать доступ: /revoke USER_ID"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        parts = message.text.split()
        if len(parts) >= 2:
            target_id = int(parts[1])
            await revoke_access(target_id)
            await message.answer(f"❌ Доступ забран!\n\nUser ID: {target_id}")
        else:
            await message.answer("❌ Формат: /revoke USER_ID\n\nПример: /revoke 123456789")
    except ValueError:
        await message.answer("❌ Неверный ID пользователя")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


async def cmd_broadcast(message: types.Message):
    """Начать рассылку"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    broadcast_state[message.from_user.id] = "waiting_message"
    await message.answer(
        "📤 <b>РАССЫЛКА</b>\n\n"
        "Отправь сообщение которое хочешь разослать всем пользователям.\n\n"
        "Для отмены отправь /cancel",
        parse_mode="HTML"
    )


async def do_broadcast(message: types.Message, text: str):
    """Выполнить рассылку"""
    bot = Bot.get_current()
    
    users = await get_all_users()
    sent = 0
    failed = 0
    
    status_msg = await bot.send_message(
        message.chat.id,
        f"📤 Рассылка началась...\n\n👥 Всего: {len(users)}"
    )
    
    for uid in users:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
        except:
            failed += 1
        
        if (sent + failed) % 10 == 0:
            try:
                await status_msg.edit_text(
                    f"📤 Рассылка...\n\n"
                    f"✅ Отправлено: {sent}\n"
                    f"❌ Ошибок: {failed}\n"
                    f"📊 Осталось: {len(users) - sent - failed}"
                )
            except:
                pass
    
    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}",
        parse_mode="HTML"
    )


async def cmd_cancel(message: types.Message):
    """Отмена текущего действия"""
    user_id = message.from_user.id
    if user_id in broadcast_state:
        broadcast_state.pop(user_id, None)
        broadcast_state.pop(f"{user_id}_text", None)
        await message.answer("❌ Отменено")


# ==================== РЕГИСТРАЦИЯ ХЕНДЛЕРОВ ====================
def setup_handlers(dp: Dispatcher):
    """Регистрация всех обработчиков"""
    
    # Команды
    dp.register_message_handler(cmd_start, commands=["start"])
    dp.register_message_handler(cmd_admin, commands=["admin"])
    dp.register_message_handler(cmd_grant, commands=["grant"])
    dp.register_message_handler(cmd_revoke, commands=["revoke"])
    dp.register_message_handler(cmd_broadcast, commands=["broadcast"])
    dp.register_message_handler(cmd_cancel, commands=["cancel"])
    
    # Callback
    dp.register_callback_query_handler(handle_callbacks)
    
    # Текстовые сообщения
    @dp.message_handler(content_types=["text"])
    async def text_handler(message: types.Message):
        user_id = message.from_user.id
        
        # Рассылка
        if user_id in broadcast_state and broadcast_state[user_id] == "waiting_message":
            if user_id in ADMIN_IDS:
                broadcast_state[f"{user_id}_text"] = message.text
                broadcast_state[user_id] = "confirm"
                
                text = f"📤 <b>ПОДТВЕРДИ РАССЫЛКУ</b>\n\n"
                text += f"<b>Сообщение:</b>\n{message.text}\n\n"
                text += "Отправить всем пользователям?"
                
                kb = InlineKeyboardMarkup()
                kb.add(
                    InlineKeyboardButton("✅ Отправить", callback_data="admin_confirm_broadcast"),
                    InlineKeyboardButton("❌ Отмена", callback_data="admin_cancel")
                )
                await message.answer(text, reply_markup=kb, parse_mode="HTML")
                return
        
        # Промокод
        handled = await handle_promo_code(message)
        if not handled:
            lang = await get_user_lang(message.from_user.id)
            paid = await is_paid(message.from_user.id)
            await show_main_menu(message, lang, paid, is_start=True)


# Алиас для совместимости
register_handlers = setup_handlers
