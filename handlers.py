"""
handlers.py - Обработчики команд и кнопок (полная версия)
"""
import time
import asyncio
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_IDS, SUPPORT_URL, t, BOT_NAME
from config import IMG_START, IMG_ALERTS, IMG_GUIDE, IMG_PAYWALL, IMG_REF
from database import *
from indicators import fetch_price
import httpx

# Состояния пользователей для диалогов
USER_STATES = {}

# ==================== HELPER FUNCTIONS ====================
def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

async def send_message_safe_local(bot, user_id: int, text: str, **kwargs):
    """Локальная версия для handlers"""
    from aiogram.utils.exceptions import RetryAfter, TelegramAPIError
    try:
        await bot.send_message(user_id, text, **kwargs)
        return True
    except RetryAfter as e:
        await asyncio.sleep(e.timeout)
        return await send_message_safe_local(bot, user_id, text, **kwargs)
    except TelegramAPIError:
        return False

async def send_photo_or_text(message_or_call, photo_url: str, text: str, reply_markup=None, is_callback=False):
    """Отправить фото если есть URL, иначе текст"""
    try:
        if photo_url:
            if is_callback:
                try:
                    await message_or_call.message.delete()
                except:
                    pass
                await message_or_call.message.answer_photo(
                    photo=photo_url,
                    caption=text,
                    reply_markup=reply_markup
                )
            else:
                await message_or_call.answer_photo(
                    photo=photo_url,
                    caption=text,
                    reply_markup=reply_markup
                )
        else:
            if is_callback:
                await message_or_call.message.edit_text(text, reply_markup=reply_markup)
            else:
                await message_or_call.answer(text, reply_markup=reply_markup)
    except Exception:
        if is_callback:
            try:
                await message_or_call.message.edit_text(text, reply_markup=reply_markup)
            except:
                await message_or_call.message.answer(text, reply_markup=reply_markup)
        else:
            await message_or_call.answer(text, reply_markup=reply_markup)

# ==================== KEYBOARDS ====================
def main_menu_kb(is_admin_user: bool, is_paid_user: bool, lang: str = "ru"):
    kb = InlineKeyboardMarkup(row_width=2)
    if is_paid_user:
        kb.add(
            InlineKeyboardButton(t(lang, "btn_alerts"), callback_data="menu_alerts"),
            InlineKeyboardButton(t(lang, "btn_ref"), callback_data="menu_ref")
        )
    kb.add(
        InlineKeyboardButton(t(lang, "btn_guide"), callback_data="menu_guide"),
        InlineKeyboardButton(t(lang, "btn_support"), url=SUPPORT_URL)
    )
    if not is_paid_user:
        kb.add(InlineKeyboardButton(t(lang, "btn_unlock"), callback_data="menu_pay"))
    if is_admin_user:
        kb.add(InlineKeyboardButton(t(lang, "btn_admin"), callback_data="menu_admin"))
    kb.add(InlineKeyboardButton("🌐 Language", callback_data="change_lang"))
    return kb

def alerts_kb(user_pairs: list, lang: str = "ru"):
    from config import DEFAULT_PAIRS
    kb = InlineKeyboardMarkup(row_width=2)
    for pair in DEFAULT_PAIRS:
        emoji = "✅" if pair in user_pairs else "➕"
        kb.add(InlineKeyboardButton(f"{emoji} {pair}", callback_data=f"toggle_{pair}"))
    
    add_btn = t(lang, "add_custom_coin")
    my_btn = t(lang, "my_coins")
    info_btn = t(lang, "how_it_works")
    
    kb.add(
        InlineKeyboardButton(add_btn, callback_data="add_custom"),
        InlineKeyboardButton(my_btn, callback_data="my_pairs")
    )
    kb.add(InlineKeyboardButton(info_btn, callback_data="alerts_info"))
    kb.add(InlineKeyboardButton(t(lang, "btn_back"), callback_data="back_main"))
    return kb

def ref_kb(lang: str = "ru"):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔗 " + ("Моя ссылка" if lang == "ru" else "My link"), callback_data="ref_link"),
        InlineKeyboardButton("💰 " + ("Баланс" if lang == "ru" else "Balance"), callback_data="ref_balance")
    )
    kb.add(
        InlineKeyboardButton("💎 " + ("Вывод (крипта)" if lang == "ru" else "Withdraw (crypto)"), callback_data="ref_withdraw_crypto"),
        InlineKeyboardButton("⭐ " + ("Вывод (Stars)" if lang == "ru" else "Withdraw (Stars)"), callback_data="ref_withdraw_stars")
    )
    kb.add(InlineKeyboardButton("📖 " + ("Гайд" if lang == "ru" else "Guide"), callback_data="ref_guide"))
    kb.add(InlineKeyboardButton(t(lang, "btn_back"), callback_data="back_main"))
    return kb

def pay_kb(lang: str = "ru"):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("⭐ " + t(lang, "pay_stars"), callback_data="pay_stars"),
        InlineKeyboardButton("💎 " + t(lang, "pay_crypto"), callback_data="pay_crypto")
    )
    kb.add(InlineKeyboardButton("🎟 " + t(lang, "pay_code"), callback_data="pay_code"))
    kb.add(InlineKeyboardButton(t(lang, "btn_back"), callback_data="back_main"))
    return kb

def admin_kb(lang: str = "ru"):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📊 " + ("Статистика" if lang == "ru" else "Statistics"), callback_data="adm_stats"),
        InlineKeyboardButton("📢 " + ("Рассылка" if lang == "ru" else "Broadcast"), callback_data="adm_broadcast")
    )
    kb.add(
        InlineKeyboardButton("✅ " + ("Выдать доступ" if lang == "ru" else "Grant access"), callback_data="adm_grant"),
        InlineKeyboardButton("💰 " + ("Начислить" if lang == "ru" else "Add balance"), callback_data="adm_give")
    )
    kb.add(InlineKeyboardButton(t(lang, "btn_back"), callback_data="back_main"))
    return kb

# ==================== SETUP HANDLERS ====================
def setup_handlers(dp):
    """Регистрация всех хендлеров"""
    
    # ==================== MAIN COMMANDS ====================
    async def show_language_selection(message: types.Message):
        """Показать выбор языка для новых пользователей"""
        text = "👋 <b>Welcome! / Привет!</b>\n\n"
        text += "🌐 Please select your language\n"
        text += "🌐 Пожалуйста, выбери свой язык"
        
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("🇷🇺 Русский", callback_data="first_lang_ru"),
            InlineKeyboardButton("🇬🇧 English", callback_data="first_lang_en")
        )
        
        if IMG_START:
            await message.answer_photo(photo=IMG_START, caption=text, reply_markup=kb)
        else:
            await message.answer(text, reply_markup=kb)
    
    @dp.message_handler(commands=["start"])
    async def cmd_start(message: types.Message):
        uid = message.from_user.id
        args = message.get_args()
        invited_by = int(args) if args and args.isdigit() and int(args) != uid else None
        
        # Проверяем, новый ли пользователь
        conn = await db_pool.acquire()
        try:
            cursor = await conn.execute("SELECT id FROM users WHERE id=?", (uid,))
            existing_user = await cursor.fetchone()
            
            if not existing_user:
                # Новый пользователь - создаём запись
                await conn.execute(
                    "INSERT INTO users(id, invited_by, created_ts) VALUES(?,?,?)",
                    (uid, invited_by, int(time.time()))
                )
                await conn.commit()
                
                # Показываем выбор языка для новых пользователей
                await show_language_selection(message)
                return
        finally:
            await db_pool.release(conn)
        
        # Существующий пользователь - показываем главное меню
        lang = await get_user_lang(uid)
        text = t(lang, "start_text")
        
        paid = await is_paid(uid)
        await send_photo_or_text(message, IMG_START, text, main_menu_kb(is_admin(uid), paid, lang))
    
    @dp.callback_query_handler(lambda c: c.data.startswith("first_lang_"))
    async def set_first_language(call: types.CallbackQuery):
        """Установить язык при первом запуске"""
        uid = call.from_user.id
        lang = call.data.split("_")[2]  # ru или en
        
        # Сохраняем язык
        await set_user_lang(uid, lang)
        
        # Показываем главное меню с выбранным языком
        text = t(lang, "start_text")
        paid = await is_paid(uid)
        
        try:
            await call.message.delete()
        except:
            pass
        
        await send_photo_or_text(call, IMG_START, text, main_menu_kb(is_admin(uid), paid, lang))
        await call.answer()
    
    # ==================== LANGUAGE ====================
    @dp.callback_query_handler(lambda c: c.data == "change_lang")
    async def change_lang_menu(call: types.CallbackQuery):
        """Меню выбора языка"""
        text = "🌐 <b>Choose Language / Выбери язык</b>"
        
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
        )
        kb.add(InlineKeyboardButton("⬅️ Назад / Back", callback_data="back_main"))
        
        try:
            await call.message.edit_text(text, reply_markup=kb)
        except:
            await call.message.answer(text, reply_markup=kb)
        await call.answer()
    
    @dp.callback_query_handler(lambda c: c.data.startswith("lang_"))
    async def set_language(call: types.CallbackQuery):
        """Установить язык"""
        lang = call.data.split("_")[1]
        await set_user_lang(call.from_user.id, lang)
        
        await call.answer(t(lang, "language_changed"), show_alert=True)
        await back_main(call)
    
    # ==================== NAVIGATION ====================
    @dp.callback_query_handler(lambda c: c.data == "back_main")
    async def back_main(call: types.CallbackQuery):
        lang = await get_user_lang(call.from_user.id)
        paid = await is_paid(call.from_user.id)
        
        text = t(lang, "main_menu")
        await send_photo_or_text(call, IMG_START, text, main_menu_kb(is_admin(call.from_user.id), paid, lang), is_callback=True)
        await call.answer()
    
    # ==================== ALERTS ====================
    @dp.callback_query_handler(lambda c: c.data == "menu_alerts")
    async def menu_alerts(call: types.CallbackQuery):
        uid = call.from_user.id
        lang = await get_user_lang(uid)
        
        if not await is_paid(uid):
            await call.answer(t(lang, "access_required"), show_alert=True)
            return
        
        pairs = await get_user_pairs(uid)
        text = t(lang, "alerts_title", count=len(pairs))
        
        await send_photo_or_text(call, IMG_ALERTS, text, alerts_kb(pairs, lang), is_callback=True)
        await call.answer()
    
    @dp.callback_query_handler(lambda c: c.data.startswith("toggle_"))
    async def toggle_pair(call: types.CallbackQuery):
        uid = call.from_user.id
        lang = await get_user_lang(uid)
        
        if not await is_paid(uid):
            await call.answer(t(lang, "access_required"), show_alert=True)
            return
        
        pair = call.data.split("_", 1)[1]
        pairs = await get_user_pairs(uid)
        
        if pair in pairs:
            await remove_user_pair(uid, pair)
            await call.answer(t(lang, "coin_removed", pair=pair))
        else:
            if len(pairs) >= 10:
                await call.answer(t(lang, "max_coins"), show_alert=True)
                return
            await add_user_pair(uid, pair)
            await call.answer(t(lang, "coin_added", pair=pair))
        
        await menu_alerts(call)
    
    @dp.callback_query_handler(lambda c: c.data == "add_custom")
    async def add_custom(call: types.CallbackQuery):
        uid = call.from_user.id
        lang = await get_user_lang(uid)
        pairs = await get_user_pairs(uid)
        
        if len(pairs) >= 10:
            await call.answer(t(lang, "max_coins"), show_alert=True)
            return
        
        USER_STATES[uid] = {"mode": "waiting_custom_pair"}
        text = t(lang, "send_coin_symbol")
        
        try:
            await call.message.edit_text(text, reply_markup=alerts_kb(pairs, lang))
        except:
            await call.message.answer(text, reply_markup=alerts_kb(pairs, lang))
        await call.answer()
    
    @dp.message_handler(lambda m: USER_STATES.get(m.from_user.id, {}).get("mode") == "waiting_custom_pair")
    async def handle_custom_pair(message: types.Message):
        uid = message.from_user.id
        lang = await get_user_lang(uid)
        pair = message.text.strip().upper()
        
        if not pair.endswith("USDT") or len(pair) < 6:
            await message.answer(t(lang, "invalid_format"))
            return
        
        async with httpx.AsyncClient() as client:
            price_data = await fetch_price(client, pair)
            if not price_data:
                await message.answer(t(lang, "pair_not_found", pair=pair))
                return
        
        await add_user_pair(uid, pair)
        USER_STATES.pop(uid, None)
        await message.answer(t(lang, "coin_added", pair=pair))
    
    @dp.callback_query_handler(lambda c: c.data == "my_pairs")
    async def my_pairs(call: types.CallbackQuery):
        lang = await get_user_lang(call.from_user.id)
        pairs = await get_user_pairs(call.from_user.id)
        
        if not pairs:
            await call.answer(t(lang, "no_active_coins"), show_alert=True)
            return
        
        title = "📋 <b>" + t(lang, "my_coins") + "</b>\n\n"
        text = title + "\n".join(f"• {p}" for p in pairs)
        
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🗑 " + t(lang, "all_removed"), callback_data="clear_all"))
        kb.add(InlineKeyboardButton(t(lang, "btn_back"), callback_data="menu_alerts"))
        
        try:
            await call.message.edit_text(text, reply_markup=kb)
        except:
            await call.message.answer(text, reply_markup=kb)
        await call.answer()
    
    @dp.callback_query_handler(lambda c: c.data == "clear_all")
    async def clear_all(call: types.CallbackQuery):
        lang = await get_user_lang(call.from_user.id)
        await clear_user_pairs(call.from_user.id)
        await call.answer(t(lang, "all_removed"))
        await menu_alerts(call)
    
    @dp.callback_query_handler(lambda c: c.data == "alerts_info")
    async def alerts_info(call: types.CallbackQuery):
        lang = await get_user_lang(call.from_user.id)
        
        text = t(lang, "guide_title") + "\n\n"
        text += t(lang, "guide_step1") + "\n"
        text += t(lang, "guide_step2") + "\n"
        text += t(lang, "guide_step3") + "\n\n"
        text += t(lang, "guide_signal_info")
        
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(t(lang, "btn_back"), callback_data="menu_alerts"))
        
        try:
            await call.message.edit_text(text, reply_markup=kb)
        except:
            await call.message.answer(text, reply_markup=kb)
        await call.answer()
    
    # ==================== PAYMENT ====================
    @dp.callback_query_handler(lambda c: c.data == "menu_pay")
    async def menu_pay(call: types.CallbackQuery):
        lang = await get_user_lang(call.from_user.id)
        text = t(lang, "payment_title") + "\n\n" + t(lang, "payment_features")
        
        await send_photo_or_text(call, IMG_PAYWALL, text, pay_kb(lang), is_callback=True)
        await call.answer()
    
    @dp.callback_query_handler(lambda c: c.data == "pay_stars")
    async def pay_stars(call: types.CallbackQuery):
        lang = await get_user_lang(call.from_user.id)
        await call.answer(t(lang, "in_development"), show_alert=True)
    
    @dp.callback_query_handler(lambda c: c.data == "pay_crypto")
    async def pay_crypto(call: types.CallbackQuery):
        lang = await get_user_lang(call.from_user.id)
        text = t(lang, "crypto_payment_info", support_url=SUPPORT_URL)
        
        try:
            await call.message.edit_text(text, reply_markup=pay_kb(lang))
        except:
            await call.message.answer(text, reply_markup=pay_kb(lang))
        await call.answer()
    
    @dp.callback_query_handler(lambda c: c.data == "pay_code")
    async def pay_code(call: types.CallbackQuery):
        lang = await get_user_lang(call.from_user.id)
        USER_STATES[call.from_user.id] = {"mode": "waiting_promo"}
        text = t(lang, "send_promo")
        
        try:
            await call.message.edit_text(text, reply_markup=pay_kb(lang))
        except:
            await call.message.answer(text, reply_markup=pay_kb(lang))
        await call.answer()
    
    @dp.message_handler(lambda m: USER_STATES.get(m.from_user.id, {}).get("mode") == "waiting_promo")
    async def handle_promo(message: types.Message):
        lang = await get_user_lang(message.from_user.id)
        await grant_access(message.from_user.id)
        USER_STATES.pop(message.from_user.id, None)
        await message.answer(t(lang, "access_granted"))
    
    # ==================== REFERRAL ====================
    @dp.callback_query_handler(lambda c: c.data == "menu_ref")
    async def menu_ref(call: types.CallbackQuery):
        lang = await get_user_lang(call.from_user.id)
        text = t(lang, "ref_title")
        await send_photo_or_text(call, IMG_REF, text, ref_kb(lang), is_callback=True)
        await call.answer()
    
    @dp.callback_query_handler(lambda c: c.data == "ref_link")
    async def ref_link(call: types.CallbackQuery):
        lang = await get_user_lang(call.from_user.id)
        from aiogram import Bot
        bot = Bot.get_current()
        me = await bot.get_me()
        link = f"https://t.me/{me.username}?start={call.from_user.id}"
        text = t(lang, "ref_link", link=link)
        
        try:
            await call.message.edit_text(text, reply_markup=ref_kb(lang), disable_web_page_preview=True)
        except:
            await call.message.answer(text, reply_markup=ref_kb(lang), disable_web_page_preview=True)
        await call.answer()
    
    @dp.callback_query_handler(lambda c: c.data == "ref_balance")
    async def ref_balance_handler(call: types.CallbackQuery):
        lang = await get_user_lang(call.from_user.id)
        balance = await get_user_balance(call.from_user.id)
        refs = await get_user_refs_count(call.from_user.id)
        
        text = t(lang, "ref_balance", balance=balance, refs=refs)
        try:
            await call.message.edit_text(text, reply_markup=ref_kb(lang))
        except:
            await call.message.answer(text, reply_markup=ref_kb(lang))
        await call.answer()
    
    @dp.callback_query_handler(lambda c: c.data in ["ref_withdraw_crypto", "ref_withdraw_stars"])
    async def ref_withdraw(call: types.CallbackQuery):
        lang = await get_user_lang(call.from_user.id)
        
        if call.data == "ref_withdraw_crypto":
            text = t(lang, "withdraw_crypto_format")
        else:
            text = t(lang, "withdraw_stars_format")
        
        try:
            await call.message.edit_text(text, reply_markup=ref_kb(lang))
        except:
            await call.message.answer(text, reply_markup=ref_kb(lang))
        await call.answer()
    
    @dp.callback_query_handler(lambda c: c.data == "ref_guide")
    async def ref_guide(call: types.CallbackQuery):
        lang = await get_user_lang(call.from_user.id)
        text = t(lang, "ref_guide_text")
        
        try:
            await call.message.edit_text(text, reply_markup=ref_kb(lang))
        except:
            await call.message.answer(text, reply_markup=ref_kb(lang))
        await call.answer()
    
    @dp.message_handler(commands=["withdraw"])
    async def cmd_withdraw(message: types.Message):
        lang = await get_user_lang(message.from_user.id)
        parts = message.text.split()
        
        if len(parts) != 5:
            await message.reply(t(lang, "withdraw_invalid_format"))
            return
        
        try:
            amount = float(parts[4])
        except:
            await message.reply(t(lang, "withdraw_invalid_amount"))
            return
        
        if amount < 20:
            await message.reply(t(lang, "withdraw_min_amount"))
            return
        
        await message.reply(t(lang, "withdraw_accepted", amount=amount, currency=parts[1]))
        
        from aiogram import Bot
        bot = Bot.get_current()
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"💸 Вывод\nUser: {message.from_user.id}\n{parts[1]} {parts[2]}\nАдрес: {parts[3]}\nСумма: {amount}"
                )
            except:
                pass
    
    @dp.message_handler(commands=["withdraw_stars"])
    async def cmd_withdraw_stars(message: types.Message):
        lang = await get_user_lang(message.from_user.id)
        parts = message.text.split()
        
        if len(parts) != 2:
            await message.reply(t(lang, "withdraw_stars_format"))
            return
        
        try:
            amount = int(parts[1])
        except:
            await message.reply(t(lang, "withdraw_invalid_amount"))
            return
        
        if amount < 20:
            await message.reply(t(lang, "withdraw_min_amount"))
            return
        
        await message.reply(t(lang, "withdraw_accepted", amount=amount, currency="Stars"))
    
    # ==================== GUIDE ====================
    @dp.callback_query_handler(lambda c: c.data == "menu_guide")
    async def menu_guide(call: types.CallbackQuery):
        lang = await get_user_lang(call.from_user.id)
        
        text = t(lang, "guide_title") + "\n\n"
        text += t(lang, "guide_step1") + "\n"
        text += t(lang, "guide_step2") + "\n"
        text += t(lang, "guide_step3") + "\n\n"
        text += t(lang, "guide_signal_info") + "\n\n"
        text += t(lang, "guide_disclaimer")
        
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(t(lang, "btn_back"), callback_data="back_main"))
        
        await send_photo_or_text(call, IMG_GUIDE, text, kb, is_callback=True)
        await call.answer()
    
    # ==================== ADMIN ====================
    @dp.callback_query_handler(lambda c: c.data == "menu_admin")
    async def menu_admin(call: types.CallbackQuery):
        lang = await get_user_lang(call.from_user.id)
        
        if not is_admin(call.from_user.id):
            await call.answer(t(lang, "admin_no_access"), show_alert=True)
            return
        
        try:
            await call.message.edit_text(t(lang, "admin_title"), reply_markup=admin_kb(lang))
        except:
            await call.message.answer(t(lang, "admin_title"), reply_markup=admin_kb(lang))
        await call.answer()
    
    @dp.callback_query_handler(lambda c: c.data == "adm_stats")
    async def adm_stats(call: types.CallbackQuery):
        if not is_admin(call.from_user.id):
            return
        
        lang = await get_user_lang(call.from_user.id)
        total = await get_users_count()
        paid = await get_paid_users_count()
        active = await get_active_users_count()
        
        text = t(lang, "admin_stats", total=total, paid=paid, active=active)
        try:
            await call.message.edit_text(text, reply_markup=admin_kb(lang))
        except:
            await call.message.answer(text, reply_markup=admin_kb(lang))
        await call.answer()
    
    @dp.callback_query_handler(lambda c: c.data == "adm_broadcast")
    async def adm_broadcast(call: types.CallbackQuery):
        if not is_admin(call.from_user.id):
            return
        
        lang = await get_user_lang(call.from_user.id)
        USER_STATES[call.from_user.id] = {"mode": "admin_broadcast"}
        
        try:
            await call.message.edit_text(t(lang, "admin_send_broadcast"), reply_markup=admin_kb(lang))
        except:
            await call.message.answer(t(lang, "admin_send_broadcast"), reply_markup=admin_kb(lang))
        await call.answer()
    
    @dp.message_handler(lambda m: USER_STATES.get(m.from_user.id, {}).get("mode") == "admin_broadcast")
    async def handle_broadcast(message: types.Message):
        if not is_admin(message.from_user.id):
            return
        
        lang = await get_user_lang(message.from_user.id)
        text = message.html_text
        users = await get_all_user_ids()
        
        from aiogram import Bot
        from config import BATCH_SEND_DELAY
        bot = Bot.get_current()
        
        sent = 0
        for user_id in users:
            if await send_message_safe_local(bot, user_id, text, disable_web_page_preview=True):
                sent += 1
            await asyncio.sleep(BATCH_SEND_DELAY)
        
        USER_STATES.pop(message.from_user.id, None)
        await message.reply(t(lang, "admin_broadcast_done", sent=sent, total=len(users)))
    
    @dp.callback_query_handler(lambda c: c.data == "adm_grant")
    async def adm_grant(call: types.CallbackQuery):
        if not is_admin(call.from_user.id):
            return
        
        lang = await get_user_lang(call.from_user.id)
        USER_STATES[call.from_user.id] = {"mode": "admin_grant"}
        
        try:
            await call.message.edit_text(t(lang, "admin_send_user_id"), reply_markup=admin_kb(lang))
        except:
            await call.message.answer(t(lang, "admin_send_user_id"), reply_markup=admin_kb(lang))
        await call.answer()
    
    @dp.message_handler(lambda m: USER_STATES.get(m.from_user.id, {}).get("mode") == "admin_grant")
    async def handle_grant(message: types.Message):
        if not is_admin(message.from_user.id):
            return
        
        lang = await get_user_lang(message.from_user.id)
        
        try:
            uid = int(message.text.strip())
        except:
            await message.reply(t(lang, "admin_invalid_id"))
            return
        
        await grant_access(uid)
        USER_STATES.pop(message.from_user.id, None)
        await message.reply(t(lang, "admin_access_granted", uid=uid))
        
        from aiogram import Bot
        bot = Bot.get_current()
        try:
            await bot.send_message(uid, t(lang, "access_granted"))
        except:
            pass
    
    @dp.callback_query_handler(lambda c: c.data == "adm_give")
    async def adm_give(call: types.CallbackQuery):
        if not is_admin(call.from_user.id):
            return
        
        lang = await get_user_lang(call.from_user.id)
        USER_STATES[call.from_user.id] = {"mode": "admin_give_uid"}
        
        try:
            await call.message.edit_text(t(lang, "admin_send_user_id"), reply_markup=admin_kb(lang))
        except:
            await call.message.answer(t(lang, "admin_send_user_id"), reply_markup=admin_kb(lang))
        await call.answer()
    
    @dp.message_handler(lambda m: USER_STATES.get(m.from_user.id, {}).get("mode") == "admin_give_uid")
    async def handle_give_uid(message: types.Message):
        if not is_admin(message.from_user.id):
            return
        
        lang = await get_user_lang(message.from_user.id)
        
        try:
            uid = int(message.text.strip())
        except:
            await message.reply(t(lang, "admin_invalid_id"))
            return
        
        USER_STATES[message.from_user.id] = {"mode": "admin_give_amount", "target_id": uid}
        await message.reply(t(lang, "admin_send_amount"))
    
    @dp.message_handler(lambda m: USER_STATES.get(m.from_user.id, {}).get("mode") == "admin_give_amount")
    async def handle_give_amount(message: types.Message):
        if not is_admin(message.from_user.id):
            return
        
        lang = await get_user_lang(message.from_user.id)
        
        try:
            amount = float(message.text.strip())
        except:
            await message.reply(t(lang, "withdraw_invalid_amount"))
            return
        
        uid = USER_STATES[message.from_user.id]["target_id"]
        await add_balance(uid, amount)
        
        USER_STATES.pop(message.from_user.id, None)
        await message.reply(t(lang, "admin_balance_added", amount=amount, uid=uid))
    
    # ==================== PnL КОМАНДЫ ====================
    from pnl_handlers import cmd_stats, cmd_active, stats_period_callback, stats_pairs_callback
    
    @dp.message_handler(commands=["stats"])
    async def handle_stats(message: types.Message):
        """Команда /stats - статистика PnL"""
        await cmd_stats(message)
    
    @dp.message_handler(commands=["active"])
    async def handle_active(message: types.Message):
        """Команда /active - активные сигналы"""
        await cmd_active(message)
    
    @dp.callback_query_handler(lambda c: c.data.startswith("stats_") and c.data.split("_")[1].isdigit())
    async def handle_stats_period(call: types.CallbackQuery):
        """Выбор периода статистики"""
        await stats_period_callback(call)
    
    @dp.callback_query_handler(lambda c: c.data == "stats_pairs")
    async def handle_stats_pairs(call: types.CallbackQuery):
        """Статистика по парам"""
        await stats_pairs_callback(call)
    
    @dp.callback_query_handler(lambda c: c.data == "show_stats")
    async def menu_show_stats(call: types.CallbackQuery):
        """Показать статистику из главного меню"""
        message = call.message
        message.from_user = call.from_user
        await cmd_stats(message)
        await call.answer()
