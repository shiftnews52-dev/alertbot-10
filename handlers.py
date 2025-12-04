"""
handlers.py - ПРОСТАЯ ВЕРСИЯ
- При переходе удаляется старое сообщение, открывается новое
- Убрана статистика
- Простой дизайн
"""
import logging
from aiogram import Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_IDS, DEFAULT_PAIRS
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
    }
}

# ==================== ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ====================
async def delete_and_send(message: types.Message, text: str, kb: InlineKeyboardMarkup):
    """Удалить старое сообщение и отправить новое"""
    try:
        await message.delete()
    except:
        pass
    
    # Получаем chat_id из сообщения
    chat_id = message.chat.id
    
    # Отправляем новое сообщение
    from aiogram import Bot
    bot = Bot.get_current()
    await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")


# ==================== /start ====================
async def cmd_start(message: types.Message):
    """Команда /start"""
    user_id = message.from_user.id
    
    if not await user_exists(user_id):
        await add_user(user_id, "ru")
    
    lang = await get_user_lang(user_id)
    paid = await is_paid(user_id)
    
    await show_main_menu(message, lang, paid, is_start=True)


async def show_main_menu(message: types.Message, lang: str, paid: bool, is_start: bool = False):
    """Главное меню"""
    
    if paid:
        if lang == "en":
            text = "🎯 <b>Alpha Entry Bot</b>\n\n"
            text += "✅ <b>PREMIUM ACCESS</b>\n\n"
            text += "You receive quality trading signals"
        else:
            text = "🎯 <b>Alpha Entry Bot</b>\n\n"
            text += "✅ <b>ПРЕМИУМ ДОСТУП</b>\n\n"
            text += "Ты получаешь качественные торговые сигналы"
    else:
        if lang == "en":
            text = "🎯 <b>Alpha Entry Bot</b>\n\n"
            text += "Professional crypto signals\n\n"
            text += "💡 Have a promo code? Just send it!"
        else:
            text = "🎯 <b>Alpha Entry Bot</b>\n\n"
            text += "Профессиональные крипто сигналы\n\n"
            text += "💡 Есть промокод? Просто отправь его!"
    
    kb = InlineKeyboardMarkup(row_width=2)
    
    if paid:
        if lang == "en":
            kb.add(InlineKeyboardButton("📈 My Coins", callback_data="menu_coins"))
            kb.add(InlineKeyboardButton("📚 Guide", callback_data="menu_guide"))
            kb.add(InlineKeyboardButton("👥 Referral", callback_data="menu_ref"))
            kb.add(InlineKeyboardButton("💬 Support", callback_data="menu_support"))
        else:
            kb.add(InlineKeyboardButton("📈 Мои монеты", callback_data="menu_coins"))
            kb.add(InlineKeyboardButton("📚 Инструкция", callback_data="menu_guide"))
            kb.add(InlineKeyboardButton("👥 Рефералка", callback_data="menu_ref"))
            kb.add(InlineKeyboardButton("💬 Поддержка", callback_data="menu_support"))
    else:
        if lang == "en":
            kb.add(InlineKeyboardButton("🔓 Get Access", callback_data="menu_pay"))
            kb.add(InlineKeyboardButton("📚 Guide", callback_data="menu_guide"))
            kb.add(InlineKeyboardButton("👥 Referral", callback_data="menu_ref"))
            kb.add(InlineKeyboardButton("💬 Support", callback_data="menu_support"))
        else:
            kb.add(InlineKeyboardButton("🔓 Получить доступ", callback_data="menu_pay"))
            kb.add(InlineKeyboardButton("📚 Инструкция", callback_data="menu_guide"))
            kb.add(InlineKeyboardButton("👥 Рефералка", callback_data="menu_ref"))
            kb.add(InlineKeyboardButton("💬 Поддержка", callback_data="menu_support"))
    
    if is_start:
        # Первый запуск - просто отправляем
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        # Переход из другого меню - удаляем старое
        await delete_and_send(message, text, kb)


# ==================== ПРОМОКОДЫ ====================
async def handle_promo_code(message: types.Message):
    """Обработка промокода"""
    user_id = message.from_user.id
    lang = await get_user_lang(user_id)
    code = message.text.strip()
    
    if code in PROMO_CODES:
        promo = PROMO_CODES[code]
        
        if promo["uses"] > 0:
            await grant_access(user_id, promo["days"])
            PROMO_CODES[code]["uses"] -= 1
            
            if lang == "en":
                text = "✅ <b>Promo code activated!</b>\n\n"
                text += "You now have premium access"
            else:
                text = "✅ <b>Промокод активирован!</b>\n\n"
                text += "Теперь у тебя премиум доступ"
            
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
    
    # Главное меню
    if data == "back_main":
        await show_main_menu(call.message, lang, paid)
        return
    
    # Мои монеты
    if data == "menu_coins":
        await show_coins_menu(call.message, lang)
        return
    
    # Инструкция
    if data == "menu_guide":
        await show_guide(call.message, lang)
        return
    
    # Поддержка
    if data == "menu_support":
        await show_support(call.message, lang)
        return
    
    # Рефералка
    if data == "menu_ref":
        await show_referral(call.message, lang, user_id)
        return
    
    # Оплата
    if data == "menu_pay":
        await show_payment_menu(call.message, lang)
        return
    
    # Включить монету
    if data.startswith("coin_on_"):
        pair = data.replace("coin_on_", "")
        await add_user_pair(user_id, pair)
        await show_coins_menu(call.message, lang)
        return
    
    # Выключить монету
    if data.startswith("coin_off_"):
        pair = data.replace("coin_off_", "")
        await remove_user_pair(user_id, pair)
        await show_coins_menu(call.message, lang)
        return
    
    # Включить все
    if data == "coins_all_on":
        for pair in DEFAULT_PAIRS:
            await add_user_pair(user_id, pair)
        await show_coins_menu(call.message, lang)
        return
    
    # Выключить все
    if data == "coins_all_off":
        for pair in DEFAULT_PAIRS:
            await remove_user_pair(user_id, pair)
        await show_coins_menu(call.message, lang)
        return
    
    # Платежи
    if data.startswith("plan_"):
        await handle_plan_selection(call)
        return
    
    if data.startswith("check_"):
        await handle_payment_check(call)
        return
    
    # ===== АДМИН CALLBACKS =====
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


# ==================== МЕНЮ МОНЕТ ====================
async def show_coins_menu(message: types.Message, lang: str):
    """Меню управления монетами"""
    user_id = message.chat.id
    user_pairs = await get_user_pairs(user_id)
    
    if lang == "en":
        text = "📈 <b>MY COINS</b>\n\n"
        if user_pairs:
            text += f"Active: {len(user_pairs)}/{len(DEFAULT_PAIRS)}\n"
            coins = ", ".join([p.replace("USDT", "") for p in user_pairs])
            text += f"<code>{coins}</code>\n\n"
        else:
            text += "⚠️ No coins selected\n\n"
        text += "Tap to toggle:"
    else:
        text = "📈 <b>МОИ МОНЕТЫ</b>\n\n"
        if user_pairs:
            text += f"Активных: {len(user_pairs)}/{len(DEFAULT_PAIRS)}\n"
            coins = ", ".join([p.replace("USDT", "") for p in user_pairs])
            text += f"<code>{coins}</code>\n\n"
        else:
            text += "⚠️ Монеты не выбраны\n\n"
        text += "Нажми чтобы вкл/выкл:"
    
    kb = InlineKeyboardMarkup(row_width=3)
    
    # Кнопки монет
    buttons = []
    for pair in DEFAULT_PAIRS:
        name = pair.replace("USDT", "")
        if pair in user_pairs:
            buttons.append(InlineKeyboardButton(f"✅ {name}", callback_data=f"coin_off_{pair}"))
        else:
            buttons.append(InlineKeyboardButton(f"⬜ {name}", callback_data=f"coin_on_{pair}"))
    
    # По 3 в ряд
    for i in range(0, len(buttons), 3):
        kb.row(*buttons[i:i+3])
    
    # Кнопки управления
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
    
    await delete_and_send(message, text, kb)


# ==================== ИНСТРУКЦИЯ ====================
async def show_guide(message: types.Message, lang: str):
    """Инструкция"""
    if lang == "en":
        text = "📚 <b>HOW TO USE</b>\n\n"
        text += "1️⃣ Select coins to track\n"
        text += "2️⃣ Wait for signals\n"
        text += "3️⃣ Open position at entry price\n"
        text += "4️⃣ Set TP and SL levels\n\n"
        text += "<b>Take Profit:</b>\n"
        text += "• TP1 - close 30%\n"
        text += "• TP2 - close 40%\n"
        text += "• TP3 - close 30%\n\n"
        text += "⚠️ Always use stop-loss!"
    else:
        text = "📚 <b>КАК ИСПОЛЬЗОВАТЬ</b>\n\n"
        text += "1️⃣ Выбери монеты для отслеживания\n"
        text += "2️⃣ Жди сигналы\n"
        text += "3️⃣ Открой позицию по цене входа\n"
        text += "4️⃣ Выстави TP и SL\n\n"
        text += "<b>Фиксация прибыли:</b>\n"
        text += "• TP1 - закрыть 30%\n"
        text += "• TP2 - закрыть 40%\n"
        text += "• TP3 - закрыть 30%\n\n"
        text += "⚠️ Всегда ставь стоп-лосс!"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Назад" if lang == "ru" else "⬅️ Back", callback_data="back_main"))
    
    await delete_and_send(message, text, kb)


# ==================== ПОДДЕРЖКА ====================
async def show_support(message: types.Message, lang: str):
    """Поддержка"""
    if lang == "en":
        text = "💬 <b>SUPPORT</b>\n\n"
        text += "Questions or problems?\n\n"
        text += "Write to: @your_support"
    else:
        text = "💬 <b>ПОДДЕРЖКА</b>\n\n"
        text += "Есть вопросы или проблемы?\n\n"
        text += "Пиши: @your_support"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Назад" if lang == "ru" else "⬅️ Back", callback_data="back_main"))
    
    await delete_and_send(message, text, kb)


# ==================== РЕФЕРАЛКА ====================
async def show_referral(message: types.Message, lang: str, user_id: int):
    """Реферальная программа"""
    # Реферальная ссылка
    bot_username = "AlphaEntryBot"  # Замени на своё
    ref_link = f"https://t.me/{bot_username}?start=ref{user_id}"
    
    if lang == "en":
        text = "👥 <b>REFERRAL PROGRAM</b>\n\n"
        text += "Invite friends and get bonuses!\n\n"
        text += f"🔗 Your link:\n<code>{ref_link}</code>\n\n"
        text += "📋 Tap to copy"
    else:
        text = "👥 <b>РЕФЕРАЛЬНАЯ ПРОГРАММА</b>\n\n"
        text += "Приглашай друзей и получай бонусы!\n\n"
        text += f"🔗 Твоя ссылка:\n<code>{ref_link}</code>\n\n"
        text += "📋 Нажми чтобы скопировать"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Назад" if lang == "ru" else "⬅️ Back", callback_data="back_main"))
    
    await delete_and_send(message, text, kb)


# ==================== АДМИН ПАНЕЛЬ ====================
async def cmd_admin(message: types.Message):
    """Админ панель"""
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
        InlineKeyboardButton("✅ Выдать доступ", callback_data="admin_grant")
    )
    kb.add(
        InlineKeyboardButton("❌ Забрать доступ", callback_data="admin_revoke"),
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


# Состояние для рассылки
broadcast_state = {}

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
    from aiogram import Bot
    bot = Bot.get_current()
    
    users = await get_all_users()
    sent = 0
    failed = 0
    
    status_msg = await bot.send_message(
        message.chat.id,
        f"📤 Рассылка началась...\n\n👥 Всего: {len(users)}"
    )
    
    for user_id in users:
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
            sent += 1
        except:
            failed += 1
        
        # Обновляем статус каждые 10 сообщений
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
    
    # Текстовые сообщения (промокоды и рассылка)
    @dp.message_handler(content_types=["text"])
    async def text_handler(message: types.Message):
        user_id = message.from_user.id
        
        # Проверяем состояние рассылки
        if user_id in broadcast_state and broadcast_state[user_id] == "waiting_message":
            if user_id in ADMIN_IDS:
                # Сохраняем текст и просим подтверждение
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
        
        # Проверяем промокод
        handled = await handle_promo_code(message)
        if not handled:
            # Не промокод - показываем меню
            lang = await get_user_lang(message.from_user.id)
            paid = await is_paid(message.from_user.id)
            await show_main_menu(message, lang, paid, is_start=True)


# Алиас для совместимости
register_handlers = setup_handlers
