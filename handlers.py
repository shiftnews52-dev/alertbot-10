"""
handlers.py - ПОЛНАЯ ВЕРСИЯ
- Картинки (IMG_START, IMG_ALERTS, IMG_REF, IMG_GUIDE)
- Промокод AbramDanke123
- Выбор языка
- Удаление сообщений при переходе
- Убрана статистика
- Админ панель
- Бэкап/Восстановление пользователей
"""
import logging
import json
from datetime import datetime
from aiogram import Dispatcher, Bot, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_IDS, DEFAULT_PAIRS, IMG_START, IMG_ALERTS, IMG_REF, IMG_PAYWALL, IMG_GUIDE
from database import (
    add_user, user_exists, get_user_lang, set_user_lang,
    is_paid, grant_access, revoke_access, get_user_pairs,
    add_user_pair, remove_user_pair, get_total_users, get_paid_users_count,
    get_all_users, export_users_backup, import_users_backup, get_backup_stats
)

# Импорты для платежей
from payment_handlers import (
    show_payment_menu,
    show_renewal_menu,
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
withdraw_state = {}  # {user_id: True} - ожидаем ввод кошелька


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
    username = message.from_user.username
    
    # Парсим ссылку:
    # ref123456 — реферальная ссылка партнёра
    # mgr_CODE — ссылка менеджера (CODE = текстовый код)
    args = message.get_args()
    referrer_id = None
    manager_code = None
    
    if args:
        if args.startswith("ref"):
            try:
                referrer_id = int(args[3:])  # ref123456 → 123456
                logger.info(f"Referral detected: user {user_id} from partner {referrer_id}")
            except ValueError:
                pass
        elif args.startswith("mgr_"):
            manager_code = args[4:]  # mgr_john → john
            logger.info(f"Manager link detected: user {user_id} from manager code '{manager_code}'")
    
    # Новый пользователь
    if not await user_exists(user_id):
        await add_user(user_id, "ru", invited_by=referrer_id, username=username)
        
        # Если пришёл по ссылке менеджера → становится партнёром
        if manager_code:
            from database import set_user_role, get_manager_by_code, increment_manager_partners
            
            # Проверяем что менеджер существует
            manager = await get_manager_by_code(manager_code)
            if manager:
                await set_user_role(user_id, "partner", manager_code)
                await increment_manager_partners(manager_code)
                logger.info(f"✅ New partner: {user_id} under manager '{manager_code}'")
            else:
                logger.warning(f"Manager code '{manager_code}' not found")
        elif referrer_id:
            logger.info(f"✅ Referrer set: {user_id} invited by {referrer_id}")
        
        await show_language_selection(message)
        return
    
    # Существующий пользователь, но пришёл по ссылке менеджера - апгрейд до партнёра
    if manager_code:
        from database import get_user_role, set_user_role, get_manager_by_code, increment_manager_partners
        current_role = await get_user_role(user_id)
        if current_role == "user":
            manager = await get_manager_by_code(manager_code)
            if manager:
                await set_user_role(user_id, "partner", manager_code)
                await increment_manager_partners(manager_code)
                logger.info(f"✅ User {user_id} upgraded to partner under manager '{manager_code}'")
    
    # Обновляем username (мог измениться)
    if username:
        from database import update_username
        await update_username(user_id, username)
    
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
            text = "✅ <b>PRO Access Activated</b>\n\n"
            text += "You're inside the system.\n"
            text += "Now your task is to follow signals and manage risk,\n"
            text += "not guess the market.\n\n"
            text += "🔔 <b>What's working for you:</b>\n"
            text += "• 🔥 RARE signals (best setups)\n"
            text += "• ⚡ HIGH signals\n"
            text += "• 📊 All MEDIUM signals instantly\n"
            text += "• Full TP1/TP2/TP3 + Stop Loss\n"
            text += "• Auto updates (entry, TP hit, SL)\n\n"
            text += "🧠 <b>Important:</b>\n"
            text += "Signals are a tool.\n"
            text += "Discipline makes profit.\n\n"
            text += "👇 Choose action:"
        else:
            # FREE ACCESS
            text = "📊 <b>FREE Access Active</b>\n\n"
            text += "You have free access to trading signals!\n\n"
            text += "✅ <b>Your FREE plan:</b>\n"
            text += "• 1 MEDIUM signal per day\n"
            text += "• 45 min delay after PRO\n"
            text += "• Entry + TP1 only\n\n"
            text += "💎 <b>Upgrade to PRO:</b>\n"
            text += "• 🔥 RARE signals (best setups)\n"
            text += "• ⚡ HIGH signals\n"
            text += "• All signals instantly\n"
            text += "• Full TP1/TP2/TP3 + Stop Loss\n"
            text += "• Auto updates when TP/SL hit\n\n"
            text += "🎁 <b>Have a promo code?</b>\n"
            text += "Just send it to get special access."
    else:
        if paid:
            text = "✅ <b>PRO доступ активирован</b>\n\n"
            text += "Ты внутри системы.\n"
            text += "Теперь твоя задача — следовать сигналам и управлять риском,\n"
            text += "а не угадывать рынок.\n\n"
            text += "🔔 <b>Что работает для тебя:</b>\n"
            text += "• 🔥 RARE сигналы (лучшие сетапы)\n"
            text += "• ⚡ HIGH сигналы\n"
            text += "• 📊 Все MEDIUM сигналы сразу\n"
            text += "• Полные TP1/TP2/TP3 + Stop Loss\n"
            text += "• Авто-апдейты (вход, TP, SL)\n\n"
            text += "🧠 <b>Важно:</b>\n"
            text += "Сигналы — это инструмент.\n"
            text += "Прибыль делает дисциплина.\n\n"
            text += "👇 Выбери действие:"
        else:
            # FREE ACCESS
            text = "📊 <b>FREE доступ активен</b>\n\n"
            text += "У тебя есть бесплатный доступ к сигналам!\n\n"
            text += "✅ <b>Твой FREE план:</b>\n"
            text += "• 1 MEDIUM сигнал в день\n"
            text += "• Задержка 45 мин после PRO\n"
            text += "• Только Entry + TP1\n\n"
            text += "💎 <b>Преимущества PRO:</b>\n"
            text += "• 🔥 RARE сигналы (лучшие сетапы)\n"
            text += "• ⚡ HIGH сигналы\n"
            text += "• Все сигналы мгновенно\n"
            text += "• Полные TP1/TP2/TP3 + Stop Loss\n"
            text += "• Авто-апдейты при достижении TP/SL\n\n"
            text += "🎁 <b>Есть промокод?</b>\n"
            text += "Просто отправь его и получи доступ."
    
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
        # FREE юзеры - кнопка Upgrade
        if lang == "en":
            kb.add(
                InlineKeyboardButton("💎 Upgrade to PRO", callback_data="menu_pay"),
                InlineKeyboardButton("📚 Guide", callback_data="menu_guide")
            )
            kb.add(
                InlineKeyboardButton("👥 Referral", callback_data="menu_ref"),
                InlineKeyboardButton("💬 Support", callback_data="menu_support")
            )
        else:
            kb.add(
                InlineKeyboardButton("💎 Перейти на PRO", callback_data="menu_pay"),
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
            text += "✅ Premium access granted!\n\n"
            text += "Now your task is to follow signals and manage risk.\n"
            text += "Signals are a tool. Discipline makes profit."
        else:
            text = "🎉 <b>ПРОМОКОД АКТИВИРОВАН!</b>\n\n"
            text += "✅ Премиум-доступ получен!\n\n"
            text += "Теперь твоя задача — следовать сигналам и управлять риском.\n"
            text += "Сигналы — это инструмент. Прибыль делает дисциплина."
        
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
        
        try:
            await call.message.delete()
        except:
            pass
        
        # Проверяем новый ли юзер (paid=0)
        is_new_user = not await is_paid(user_id)
        
        if is_new_user:
            # Показываем FREE welcome
            if new_lang == "en":
                text = "🎁 <b>WELCOME!</b>\n\n"
                text += "You now have <b>FREE access</b> to trading signals!\n\n"
                text += "📊 FREE includes:\n"
                text += "• 1 MEDIUM signal per day\n"
                text += "• 45 min delay\n"
                text += "• Entry + TP1 only\n\n"
                text += "💎 <b>PRO includes:</b>\n"
                text += "• 🔥 RARE signals (best setups)\n"
                text += "• ⚡ HIGH signals\n"
                text += "• Instant delivery\n"
                text += "• Full TP1/TP2/TP3 + Stop Loss\n\n"
                text += "Start exploring! 🚀"
            else:
                text = "🎁 <b>ДОБРО ПОЖАЛОВАТЬ!</b>\n\n"
                text += "Тебе доступен <b>FREE доступ</b> к торговым сигналам!\n\n"
                text += "📊 FREE включает:\n"
                text += "• 1 MEDIUM сигнал в день\n"
                text += "• Задержка 45 мин\n"
                text += "• Только Entry + TP1\n\n"
                text += "💎 <b>PRO включает:</b>\n"
                text += "• 🔥 RARE сигналы (лучшие сетапы)\n"
                text += "• ⚡ HIGH сигналы\n"
                text += "• Мгновенная доставка\n"
                text += "• Полные TP1/TP2/TP3 + Stop Loss\n\n"
                text += "Начинай исследовать! 🚀"
            
            kb = InlineKeyboardMarkup()
            btn_text = "🚀 Let's go!" if new_lang == "en" else "🚀 Поехали!"
            kb.add(InlineKeyboardButton(btn_text, callback_data="back_main"))
            
            await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
            await call.answer()
            return
        
        # Существующий юзер - просто меняем язык
        if new_lang == "en":
            await call.answer("✅ Language changed to English", show_alert=True)
        else:
            await call.answer("✅ Язык изменён на русский", show_alert=True)
        
        paid = await is_paid(user_id)
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
        await show_payment_menu(call, is_callback=True)
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
    if data.startswith("pay_"):
        await handle_plan_selection(call)
        return
    
    if data.startswith("check_"):
        await handle_payment_check(call)
        return
    
    # ===== ПРОДЛЕНИЕ СО СКИДКОЙ =====
    if data == "renew_discount":
        await show_renewal_menu(call, is_callback=True)
        return
    
    if data == "show_pricing":
        await show_payment_menu(call, is_callback=True)
        return
    
    if data.startswith("renew_"):
        # renew_1m, renew_3m, etc - со скидкой 25%
        from payment_handlers import handle_renewal_selection
        await handle_renewal_selection(call)
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
    
    if data == "admin_backup":
        if user_id in ADMIN_IDS:
            await call.answer("⏳ Создаю бэкап...")
            try:
                backup_data = await export_users_backup()
                backup_json = json.dumps(backup_data, ensure_ascii=False, indent=2)
                
                from io import BytesIO
                file = BytesIO(backup_json.encode('utf-8'))
                file.name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                
                caption = f"✅ <b>БЭКАП СОЗДАН</b>\n\n"
                caption += f"👥 Всего: {backup_data['total_users']}\n"
                caption += f"💎 Премиум: {backup_data['premium_users']}\n"
                caption += f"📅 {backup_data['exported_at'][:19]}\n\n"
                caption += "💾 Сохрани этот файл!"
                
                await call.message.answer_document(file, caption=caption, parse_mode="HTML")
            except Exception as e:
                await call.message.answer(f"❌ Ошибка: {e}")
        return
    
    if data == "admin_referrals":
        if user_id in ADMIN_IDS:
            from database import get_all_referral_stats
            stats = await get_all_referral_stats()
            
            if not stats:
                text = "👥 <b>РЕФЕРАЛЫ</b>\n\n"
                text += "Пока нет рефералов с балансом"
            else:
                total_pending = sum(s["earnings"] for s in stats)
                
                text = "👥 <b>СТАТИСТИКА РЕФЕРАЛОВ</b>\n\n"
                text += f"💰 Всего к выплате: <b>${total_pending:.2f}</b>\n\n"
                
                for s in stats[:15]:  # Топ 15
                    uname = f"@{s['username']}" if s.get('username') else f"ID: {s['user_id']}"
                    text += f"👤 {uname}\n"
                    text += f"   💵 Баланс: ${s['earnings']:.2f}\n"
                    text += f"   👥 Рефов: {s['total_referrals']} (💎 {s['paid_referrals']})\n"
                
                if len(stats) > 15:
                    text += f"\n... и ещё {len(stats) - 15}"
            
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="admin_back"))
            
            await delete_and_send(call.message, text, kb)
        return
    
    if data == "admin_subscribers" or data.startswith("admin_subs_page_"):
        if user_id in ADMIN_IDS:
            from database import get_paid_users_list
            
            # Определяем страницу
            if data.startswith("admin_subs_page_"):
                page = int(data.split("_")[-1])
            else:
                page = 0
            
            per_page = 20
            users = await get_paid_users_list()
            total = len(users)
            total_pages = (total + per_page - 1) // per_page  # Округление вверх
            
            # Срез для текущей страницы
            start = page * per_page
            end = start + per_page
            page_users = users[start:end]
            
            text = f"💎 <b>ПОДПИСЧИКИ</b> ({total})\n"
            text += f"📄 Страница {page + 1}/{max(1, total_pages)}\n\n"
            
            if not page_users:
                text += "Пока нет подписчиков"
            else:
                for u in page_users:
                    uname = f"@{u['username']}" if u.get('username') else "—"
                    days = f"{u['days_left']}д" if u['days_left'] is not None else "∞"
                    text += f"<code>{u['user_id']}</code> | {uname} | {days}\n"
            
            kb = InlineKeyboardMarkup(row_width=2)
            
            # Кнопки навигации
            nav_buttons = []
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_subs_page_{page - 1}"))
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton("Вперёд ➡️", callback_data=f"admin_subs_page_{page + 1}"))
            
            if nav_buttons:
                kb.add(*nav_buttons)
            
            kb.add(InlineKeyboardButton("🔙 В админку", callback_data="admin_back"))
            
            await delete_and_send(call.message, text, kb)
        return
    
    # ===== МЕНЕДЖЕРЫ =====
    if data == "admin_managers" or data.startswith("admin_mgr_page_"):
        if user_id in ADMIN_IDS:
            from database import get_all_managers
            
            if data.startswith("admin_mgr_page_"):
                page = int(data.split("_")[-1])
            else:
                page = 0
            
            per_page = 10
            managers = await get_all_managers()
            total = len(managers)
            total_pages = max(1, (total + per_page - 1) // per_page)
            
            start = page * per_page
            end = start + per_page
            page_managers = managers[start:end]
            
            text = f"👔 <b>МЕНЕДЖЕРЫ</b> ({total})\n"
            text += f"📄 Страница {page + 1}/{total_pages}\n\n"
            
            if not page_managers:
                text += "Нет менеджеров\n\n"
                text += "Добавить: <code>/addmanager CODE NAME</code>"
            else:
                for m in page_managers:
                    name = m['name'] or '—'
                    text += f"<code>{m['code']}</code> | {name}\n"
                    text += f"   👥 {m['partners_count']} партн. | 💎 {m['conversions']} конв. | 💰 ${m['balance']:.2f}\n"
            
            kb = InlineKeyboardMarkup(row_width=2)
            
            nav_buttons = []
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"admin_mgr_page_{page - 1}"))
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"admin_mgr_page_{page + 1}"))
            if nav_buttons:
                kb.add(*nav_buttons)
            
            kb.add(InlineKeyboardButton("🔙 В админку", callback_data="admin_back"))
            
            await delete_and_send(call.message, text, kb)
        return
    
    # ===== ПАРТНЁРЫ =====
    if data == "admin_partners" or data.startswith("admin_prt_page_"):
        if user_id in ADMIN_IDS:
            from database import get_partners_list
            
            if data.startswith("admin_prt_page_"):
                page = int(data.split("_")[-1])
            else:
                page = 0
            
            per_page = 15
            partners = await get_partners_list()
            total = len(partners)
            total_pages = max(1, (total + per_page - 1) // per_page)
            
            start = page * per_page
            end = start + per_page
            page_partners = partners[start:end]
            
            text = f"🤝 <b>ПАРТНЁРЫ</b> ({total})\n"
            text += f"📄 Страница {page + 1}/{total_pages}\n\n"
            
            if not page_partners:
                text += "Нет партнёров\n\n"
                text += "Партнёры появляются когда переходят по ссылке менеджера."
            else:
                for p in page_partners:
                    uname = f"@{p['username']}" if p.get('username') else "—"
                    mgr = p.get('manager_code') or "—"
                    text += f"<code>{p['user_id']}</code> | {uname} | mgr: {mgr}\n"
                    text += f"   👥 {p['referrals']} реф | 💎 {p['paid_referrals']} опл | 💰 ${p['balance']:.2f}\n"
            
            kb = InlineKeyboardMarkup(row_width=2)
            
            nav_buttons = []
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"admin_prt_page_{page - 1}"))
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"admin_prt_page_{page + 1}"))
            if nav_buttons:
                kb.add(*nav_buttons)
            
            kb.add(InlineKeyboardButton("🔙 В админку", callback_data="admin_back"))
            
            await delete_and_send(call.message, text, kb)
        return
    
    if data == "admin_payouts" or data.startswith("admin_pay_page_"):
        if user_id in ADMIN_IDS:
            from database import get_users_with_balance
            
            # Получаем всех с балансом > 0
            pending_users = await get_users_with_balance()
            
            # Пагинация
            if data.startswith("admin_pay_page_"):
                page = int(data.split("_")[-1])
            else:
                page = 0
            
            per_page = 15
            total = len(pending_users)
            total_pending = sum(u["balance"] for u in pending_users)
            total_pages = max(1, (total + per_page - 1) // per_page)
            
            start = page * per_page
            end = start + per_page
            page_users = pending_users[start:end]
            
            text = f"💰 <b>К ВЫПЛАТЕ</b>\n\n"
            text += f"👥 Всего: {total} чел.\n"
            text += f"💵 Сумма: <b>${total_pending:.2f}</b>\n"
            text += f"📄 Страница {page + 1}/{total_pages}\n\n"
            
            if not page_users:
                text += "Нет выплат"
            else:
                for u in page_users:
                    uname = f"@{u['username']}" if u.get('username') else "—"
                    role_emoji = "👔" if u['role'] == 'manager' else "🤝" if u['role'] == 'partner' else "👤"
                    text += f"{role_emoji} <code>{u['user_id']}</code> | {uname}\n"
                    text += f"   💰 <b>${u['balance']:.2f}</b>\n"
            
            text += f"\n<i>Выплата: /payout ID</i>"
            
            kb = InlineKeyboardMarkup(row_width=2)
            
            nav_buttons = []
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"admin_pay_page_{page - 1}"))
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"admin_pay_page_{page + 1}"))
            if nav_buttons:
                kb.add(*nav_buttons)
            
            kb.add(InlineKeyboardButton("🔙 В админку", callback_data="admin_back"))
            
            await delete_and_send(call.message, text, kb)
        return
    
    if data == "admin_limits":
        if user_id in ADMIN_IDS:
            from tasks import get_daily_limits_info
            
            info = get_daily_limits_info()
            
            text = "📊 <b>ЛИМИТЫ СИГНАЛОВ</b>\n\n"
            text += f"🔥 RARE: {info['rare']['current']}/{info['rare']['max']}\n"
            text += f"⚡ HIGH: {info['high']['current']}/{info['high']['max']}\n"
            text += f"📊 MEDIUM: {info['medium']['current']}/{info['medium']['max']}\n\n"
            
            # Временные окна HIGH
            text += "<b>⏰ Окна HIGH (UTC):</b>\n"
            for slot_info in info.get('high_slots', []):
                text += f"   {slot_info}\n"
            text += "\n"
            
            text += f"⏱ Cooldowns: {info['cooldowns']}\n"
            text += f"📥 Очередь: {info['queue_size']}"
            
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("🔄 Сбросить лимиты", callback_data="admin_reset_limits"))
            kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="admin_back"))
            
            await delete_and_send(call.message, text, kb)
        return
    
    if data == "admin_reset_limits":
        if user_id in ADMIN_IDS:
            from tasks import reset_daily_limits, get_daily_limits_info
            
            reset_daily_limits()
            info = get_daily_limits_info()
            
            text = "✅ <b>ЛИМИТЫ СБРОШЕНЫ!</b>\n\n"
            text += f"🔥 RARE: {info['rare']['current']}/{info['rare']['max']}\n"
            text += f"⚡ HIGH: {info['high']['current']}/{info['high']['max']}\n"
            text += f"📊 MEDIUM: {info['medium']['current']}/{info['medium']['max']}"
            
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="admin_back"))
            
            await delete_and_send(call.message, text, kb)
        return
    
    # Обработка запроса на вывод рефералки
    if data == "ref_withdraw":
        from database import get_referral_stats
        stats = await get_referral_stats(user_id)
        earnings = stats["earnings"]
        lang = await get_user_lang(user_id)
        
        if earnings < MIN_WITHDRAWAL:
            text = f"❌ Minimum ${MIN_WITHDRAWAL}" if lang == "en" else f"❌ Минимум ${MIN_WITHDRAWAL}"
            await call.answer(text, show_alert=True)
            return
        
        # Запрашиваем кошелёк
        withdraw_state[user_id] = True
        
        if lang == "en":
            text = f"💰 <b>WITHDRAWAL REQUEST</b>\n\n"
            text += f"Amount: <b>${earnings:.2f}</b>\n\n"
            text += "Send your USDT wallet address (TRC20):"
        else:
            text = f"💰 <b>ЗАПРОС НА ВЫВОД</b>\n\n"
            text += f"Сумма: <b>${earnings:.2f}</b>\n\n"
            text += "Отправь адрес своего USDT кошелька (TRC20):"
        
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("❌ Отмена" if lang == "ru" else "❌ Cancel", callback_data="ref_cancel"))
        
        await delete_and_send(call.message, text, kb)
        return
    
    if data == "ref_cancel":
        withdraw_state.pop(user_id, None)
        lang = await get_user_lang(user_id)
        await show_referral(call.message, lang, user_id)
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
        text = "📘 <b>HOW TO TRADE WITH ALERT BOT</b>\n\n"
        text += "1️⃣ <b>Get a signal</b>\n"
        text += "3–5 signals per day with entry points and TP/SL.\n\n"
        text += "2️⃣ <b>Open position</b>\n"
        text += "Enter at the specified range.\n\n"
        text += "3️⃣ <b>Take profits</b>\n"
        text += "• TP1 — lock in 15%\n"
        text += "• TP2 — lock in 40%\n"
        text += "• TP3 — main profit 💰\n\n"
        text += "4️⃣ <b>Always set Stop-Loss</b>\n"
        text += "We trade discipline, not emotions.\n\n"
        text += "🎯 Average signal accuracy — 70%+"
    else:
        text = "📘 <b>КАК ТОРГОВАТЬ С ALERT BOT</b>\n\n"
        text += "1️⃣ <b>Получаешь сигнал</b>\n"
        text += "3–5 сигналов в день с точками входа и TP/SL.\n\n"
        text += "2️⃣ <b>Открываешь позицию</b>\n"
        text += "Входишь по указанному диапазону.\n\n"
        text += "3️⃣ <b>Фиксируешь прибыль</b>\n"
        text += "• TP1 — зафиксируй 15%\n"
        text += "• TP2 — зафиксируй 40%\n"
        text += "• TP3 — основной профит 💰\n\n"
        text += "4️⃣ <b>Всегда ставь Stop-Loss</b>\n"
        text += "Мы торгуем дисциплину, а не эмоции.\n\n"
        text += "🎯 Средняя точность сигналов — 70%+"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Назад" if lang == "ru" else "⬅️ Back", callback_data="back_main"))
    
    await delete_and_send(message, text, kb, IMG_GUIDE)


# ==================== РЕФЕРАЛКА ====================
from config import MIN_WITHDRAWAL

async def show_referral(message: types.Message, lang: str, user_id: int):
    """Реферальная программа с учётом роли"""
    from database import get_referral_stats, get_user_role, get_user_manager
    
    bot = Bot.get_current()
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    
    role = await get_user_role(user_id)
    stats = await get_referral_stats(user_id)
    total_refs = stats["total_referrals"]
    paid_refs = stats["paid_referrals"]
    earnings = stats["earnings"]
    
    kb = InlineKeyboardMarkup()
    
    # ===== PARTNER =====
    if role == "partner":
        ref_link = f"https://t.me/{bot_username}?start=ref{user_id}"
        manager_code = await get_user_manager(user_id)
        
        if lang == "en":
            text = "🤝 <b>PARTNER PANEL</b>\n\n"
            text += "You are a <b>Partner</b>.\n"
            text += "Share your link and earn <b>$10</b> for each paying user.\n\n"
            text += f"🔗 <b>Your referral link:</b>\n<code>{ref_link}</code>\n\n"
            text += f"👥 Users invited: <b>{total_refs}</b>\n"
            text += f"💎 Paid users: <b>{paid_refs}</b>\n"
            text += f"💰 Balance: <b>${earnings:.2f}</b>\n"
            if manager_code:
                text += f"\n👔 Your manager: <code>{manager_code}</code>"
            text += f"\n\n💵 Min withdrawal: ${MIN_WITHDRAWAL}"
        else:
            text = "🤝 <b>ПАНЕЛЬ ПАРТНЁРА</b>\n\n"
            text += "Ты — <b>Партнёр</b>.\n"
            text += "Делись ссылкой и получай <b>$10</b> за каждого оплатившего.\n\n"
            text += f"🔗 <b>Твоя реферальная ссылка:</b>\n<code>{ref_link}</code>\n\n"
            text += f"👥 Приглашено: <b>{total_refs}</b>\n"
            text += f"💎 Оплативших: <b>{paid_refs}</b>\n"
            text += f"💰 Баланс: <b>${earnings:.2f}</b>\n"
            if manager_code:
                text += f"\n👔 Твой менеджер: <code>{manager_code}</code>"
            text += f"\n\n💵 Минимум для вывода: ${MIN_WITHDRAWAL}"
    
    # ===== USER =====
    else:
        ref_link = f"https://t.me/{bot_username}?start=ref{user_id}"
        
        if lang == "en":
            text = "👥 <b>REFERRAL PROGRAM</b>\n\n"
            text += "Invite friends and earn with us 💸\n\n"
            text += "You get <b>$10</b> for each invited user who pays — no limits.\n\n"
            text += f"🔗 <b>Your personal link:</b>\n<code>{ref_link}</code>\n\n"
            text += f"💰 Your earnings: <b>${earnings:.2f}</b>\n"
            text += f"👥 Traders invited: <b>{total_refs}</b>\n"
            if paid_refs > 0:
                text += f"💎 Paid traders: <b>{paid_refs}</b>\n"
            text += f"\n💵 Minimum withdrawal: ${MIN_WITHDRAWAL}"
            text += "\n\n👉 More active traders — higher your passive income."
        else:
            text = "👥 <b>РЕФЕРАЛЬНАЯ ПРОГРАММА</b>\n\n"
            text += "Приглашай друзей и зарабатывай вместе с нами 💸\n\n"
            text += "Ты получаешь <b>$10</b> за каждого приглашённого, который оплатит подписку — без лимитов.\n\n"
            text += f"🔗 <b>Твоя персональная ссылка:</b>\n<code>{ref_link}</code>\n\n"
            text += f"💰 Твой доход: <b>${earnings:.2f}</b>\n"
            text += f"👥 Приведено трейдеров: <b>{total_refs}</b>\n"
            if paid_refs > 0:
                text += f"💎 Оплативших: <b>{paid_refs}</b>\n"
            text += f"\n💵 Минимум для вывода: ${MIN_WITHDRAWAL}"
            text += "\n\n👉 Чем больше активных трейдеров — тем выше твой пассивный доход."
    
    # Кнопка вывода
    if earnings >= MIN_WITHDRAWAL:
        btn_text = "💰 Withdraw" if lang == "en" else "💰 Вывести"
        kb.add(InlineKeyboardButton(btn_text, callback_data="ref_withdraw"))
    
    kb.add(InlineKeyboardButton("⬅️ Назад" if lang == "ru" else "⬅️ Back", callback_data="back_main"))
    
    await delete_and_send(message, text, kb, IMG_REF)


# ==================== ПОДДЕРЖКА ====================
async def show_support(message: types.Message, lang: str):
    """Поддержка"""
    if lang == "en":
        text = "💬 <b>SUPPORT</b>\n\n"
        text += "Have questions or something not working?\n"
        text += "We're here and will definitely respond 👇\n\n"
        text += "📩 Contact: @SHIFTDM\n\n"
        text += "⏱️ Average response time — up to 24 hours"
    else:
        text = "💬 <b>ПОДДЕРЖКА</b>\n\n"
        text += "Есть вопросы или что-то не работает?\n"
        text += "Мы на связи и обязательно ответим 👇\n\n"
        text += "📩 Контакт: @SHIFTDM\n\n"
        text += "⏱️ Среднее время ответа — до 24 часов"
    
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
    
    text += "📋 <b>Все команды:</b>\n\n"
    
    text += "<b>👤 Пользователи:</b>\n"
    text += "<code>/grant @user DAYS</code> — выдать доступ\n"
    text += "<code>/revoke @user</code> — забрать доступ\n"
    text += "<code>/addbalance ID SUM</code> — начислить баланс\n\n"
    
    text += "<b>👔 Менеджеры:</b>\n"
    text += "<code>/addmanager CODE NAME</code> — создать\n"
    text += "<code>/delmanager CODE</code> — удалить\n\n"
    
    text += "<b>📊 Система:</b>\n"
    text += "<code>/limits</code> — лимиты сигналов\n"
    text += "<code>/resetlimits</code> — сбросить лимиты\n"
    text += "<code>/broadcast</code> — рассылка\n"
    text += "<code>/backup</code> — создать бэкап\n"
    text += "<code>/payout ID</code> — отметить выплату\n"
    text += "<code>/testsplit ID</code> — тест распределения 💰"
    
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📤 Рассылка", callback_data="admin_broadcast"),
        InlineKeyboardButton("✅ Выдать", callback_data="admin_grant")
    )
    kb.add(
        InlineKeyboardButton("❌ Забрать", callback_data="admin_revoke"),
        InlineKeyboardButton("💾 Бэкап", callback_data="admin_backup")
    )
    kb.add(
        InlineKeyboardButton("👔 Менеджеры", callback_data="admin_managers"),
        InlineKeyboardButton("🤝 Партнёры", callback_data="admin_partners")
    )
    kb.add(
        InlineKeyboardButton("💎 Подписчики", callback_data="admin_subscribers"),
        InlineKeyboardButton("📊 Лимиты", callback_data="admin_limits")
    )
    kb.add(
        InlineKeyboardButton("💰 Выплаты", callback_data="admin_payouts"),
        InlineKeyboardButton("🔄 Обновить", callback_data="admin_refresh")
    )
    
    if is_callback:
        await delete_and_send(message, text, kb)
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


async def cmd_grant(message: types.Message):
    """Выдать доступ: /grant USER_ID|@username DAYS"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        parts = message.text.split()
        if len(parts) >= 2:
            target = parts[1]
            days = int(parts[2]) if len(parts) >= 3 else 30
            
            # Проверяем: ID или username?
            if target.startswith('@') or not target.isdigit():
                # Это username
                from database import get_user_by_username
                user = await get_user_by_username(target)
                if not user:
                    await message.answer(f"❌ Пользователь @{target.lstrip('@')} не найден в базе")
                    return
                target_id = user['user_id']
                username = user['username']
            else:
                # Это ID
                target_id = int(target)
                username = None
            
            await grant_access(target_id, days)
            
            text = f"✅ <b>Доступ выдан!</b>\n\n"
            text += f"👤 User ID: <code>{target_id}</code>\n"
            if username:
                text += f"📛 Username: @{username}\n"
            text += f"📅 Дней: <b>{days}</b>"
            await message.answer(text, parse_mode="HTML")
        else:
            await message.answer(
                "❌ <b>Формат:</b> /grant USER [DAYS]\n\n"
                "<b>Примеры:</b>\n"
                "<code>/grant 123456789 30</code>\n"
                "<code>/grant @username 30</code>\n"
                "<code>/grant username 7</code>",
                parse_mode="HTML"
            )
    except ValueError:
        await message.answer("❌ Неверный ID или количество дней")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


async def cmd_revoke(message: types.Message):
    """Забрать доступ: /revoke USER_ID|@username"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        parts = message.text.split()
        if len(parts) >= 2:
            target = parts[1]
            
            # Проверяем: ID или username?
            if target.startswith('@') or not target.isdigit():
                # Это username
                from database import get_user_by_username
                user = await get_user_by_username(target)
                if not user:
                    await message.answer(f"❌ Пользователь @{target.lstrip('@')} не найден в базе")
                    return
                target_id = user['user_id']
                username = user['username']
            else:
                # Это ID
                target_id = int(target)
                username = None
            
            await revoke_access(target_id)
            
            text = f"❌ <b>Доступ забран!</b>\n\n"
            text += f"👤 User ID: <code>{target_id}</code>"
            if username:
                text += f"\n📛 Username: @{username}"
            await message.answer(text, parse_mode="HTML")
        else:
            await message.answer(
                "❌ <b>Формат:</b> /revoke USER\n\n"
                "<b>Примеры:</b>\n"
                "<code>/revoke 123456789</code>\n"
                "<code>/revoke @username</code>",
                parse_mode="HTML"
            )
    except ValueError:
        await message.answer("❌ Неверный ID пользователя")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


async def cmd_addmanager(message: types.Message):
    """
    Добавить менеджера: /addmanager CODE [NAME]
    
    Примеры:
    /addmanager john
    /addmanager promo2024 Иван Промо
    """
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) >= 2:
            code = parts[1].lower().strip()
            name = parts[2] if len(parts) > 2 else None
            
            # Валидация кода
            if not code.isalnum() or len(code) < 2 or len(code) > 20:
                await message.answer("❌ Код должен быть 2-20 символов (буквы и цифры)")
                return
            
            from database import create_manager
            
            bot = Bot.get_current()
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            
            success = await create_manager(code, name)
            
            if success:
                link = f"https://t.me/{bot_username}?start=mgr_{code}"
                text = f"✅ <b>Менеджер создан!</b>\n\n"
                text += f"📝 Код: <code>{code}</code>\n"
                if name:
                    text += f"👤 Имя: {name}\n"
                text += f"\n🔗 <b>Ссылка для партнёров:</b>\n<code>{link}</code>\n\n"
                text += "Отправь эту ссылку менеджеру. Все кто перейдут по ней станут партнёрами."
                await message.answer(text, parse_mode="HTML")
            else:
                await message.answer(f"❌ Код '{code}' уже занят. Выбери другой.")
        else:
            await message.answer(
                "❌ <b>Формат:</b> /addmanager CODE [NAME]\n\n"
                "<b>Примеры:</b>\n"
                "<code>/addmanager john</code>\n"
                "<code>/addmanager promo2024 Иван Промо</code>\n\n"
                "CODE — уникальный код (2-20 символов)\n"
                "NAME — имя/описание (опционально)",
                parse_mode="HTML"
            )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


async def cmd_delmanager(message: types.Message):
    """Удалить менеджера: /delmanager CODE"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        parts = message.text.split()
        if len(parts) >= 2:
            code = parts[1].lower().strip()
            
            from database import get_manager_by_code, delete_manager
            
            manager = await get_manager_by_code(code)
            if not manager:
                await message.answer(f"❌ Менеджер с кодом '{code}' не найден")
                return
            
            await delete_manager(code)
            
            text = f"✅ <b>Менеджер удалён!</b>\n\n"
            text += f"📝 Код: <code>{code}</code>\n"
            if manager.get('name'):
                text += f"👤 Имя: {manager['name']}\n"
            text += f"💰 Баланс был: ${manager['balance']:.2f}"
            await message.answer(text, parse_mode="HTML")
        else:
            await message.answer("❌ Формат: /delmanager CODE\n\nПример: /delmanager john")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


async def cmd_addbalance(message: types.Message):
    """
    Начислить баланс пользователю: /addbalance ID AMOUNT
    
    Примеры:
    /addbalance 123456789 50
    /addbalance 123456789 10.5
    """
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        parts = message.text.split()
        if len(parts) >= 3:
            target_id = int(parts[1])
            amount = float(parts[2])
            
            if amount <= 0:
                await message.answer("❌ Сумма должна быть больше 0")
                return
            
            from database import add_referral_bonus, user_exists
            
            if not await user_exists(target_id):
                await message.answer(f"❌ Пользователь {target_id} не найден")
                return
            
            await add_referral_bonus(target_id, amount, 0)  # 0 = от админа
            
            text = f"✅ <b>Баланс начислен!</b>\n\n"
            text += f"👤 User ID: <code>{target_id}</code>\n"
            text += f"💰 Сумма: <b>+${amount:.2f}</b>"
            await message.answer(text, parse_mode="HTML")
        else:
            await message.answer(
                "❌ <b>Формат:</b> /addbalance ID AMOUNT\n\n"
                "<b>Примеры:</b>\n"
                "<code>/addbalance 123456789 50</code>\n"
                "<code>/addbalance 123456789 10.5</code>",
                parse_mode="HTML"
            )
    except ValueError:
        await message.answer("❌ Неверный ID или сумма")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


async def cmd_testsplit(message: types.Message):
    """
    Тест распределения денег: /testsplit USER_ID
    Показывает кто получит деньги при оплате этого юзера
    """
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        parts = message.text.split()
        if len(parts) >= 2:
            target_id = int(parts[1])
            
            from database import (
                user_exists, get_referrer, get_user_role, 
                get_user_manager, is_first_payment, get_manager_by_code
            )
            
            if not await user_exists(target_id):
                await message.answer(f"❌ Пользователь {target_id} не найден")
                return
            
            text = f"🧪 <b>ТЕСТ РАСПРЕДЕЛЕНИЯ</b>\n\n"
            text += f"👤 User ID: <code>{target_id}</code>\n\n"
            
            # Проверяем первая ли оплата
            is_first = await is_first_payment(target_id)
            if not is_first:
                text += "⚠️ <b>Это ПРОДЛЕНИЕ</b> — никто ничего не получит\n"
                text += "💵 Все $20 → тебе"
                await message.answer(text, parse_mode="HTML")
                return
            
            text += "✅ Это ПЕРВАЯ оплата\n\n"
            
            # Кто пригласил (партнёр)
            partner_id = await get_referrer(target_id)
            
            if not partner_id:
                text += "❌ Нет реферера — пришёл сам\n"
                text += "💵 Все $20 → тебе"
                await message.answer(text, parse_mode="HTML")
                return
            
            text += f"🤝 <b>Партнёр:</b> <code>{partner_id}</code>\n"
            text += f"   💰 Получит: <b>$10</b>\n\n"
            
            # Менеджер партнёра
            manager_code = await get_user_manager(partner_id)
            
            if manager_code:
                manager = await get_manager_by_code(manager_code)
                if manager:
                    text += f"👔 <b>Менеджер:</b> <code>{manager_code}</code>"
                    if manager.get('name'):
                        text += f" ({manager['name']})"
                    text += f"\n   💰 Получит: <b>$3</b>\n\n"
                    text += "💵 Тебе остаётся: <b>$7</b>"
                else:
                    text += f"⚠️ Менеджер <code>{manager_code}</code> не найден в БД!\n"
                    text += "💵 Тебе остаётся: <b>$10</b>"
            else:
                text += "👔 Менеджера нет (партнёр пришёл сам)\n"
                text += "💵 Тебе остаётся: <b>$10</b>"
            
            await message.answer(text, parse_mode="HTML")
        else:
            await message.answer(
                "❌ <b>Формат:</b> /testsplit USER_ID\n\n"
                "Покажет кто получит деньги при оплате этого юзера",
                parse_mode="HTML"
            )
    except ValueError:
        await message.answer("❌ Неверный ID")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


async def cmd_limits(message: types.Message):
    """Показать текущие лимиты сигналов: /limits"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    from tasks import get_daily_limits_info
    
    info = get_daily_limits_info()
    
    text = "📊 <b>ЛИМИТЫ СИГНАЛОВ</b>\n\n"
    text += f"🔥 RARE: {info['rare']['current']}/{info['rare']['max']}\n"
    text += f"⚡ HIGH: {info['high']['current']}/{info['high']['max']}\n"
    text += f"📊 MEDIUM: {info['medium']['current']}/{info['medium']['max']}\n\n"
    
    # Временные окна HIGH
    text += "<b>⏰ Окна HIGH (UTC):</b>\n"
    for slot_info in info.get('high_slots', []):
        text += f"   {slot_info}\n"
    text += "\n"
    
    text += f"⏱ Активных cooldown: {info['cooldowns']}\n"
    text += f"📥 В очереди: {info['queue_size']}\n\n"
    text += "Сбросить: /resetlimits"
    
    await message.answer(text, parse_mode="HTML")


async def cmd_resetlimits(message: types.Message):
    """Сбросить дневные лимиты: /resetlimits"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    from tasks import reset_daily_limits, get_daily_limits_info
    
    reset_daily_limits()
    info = get_daily_limits_info()
    
    text = "✅ <b>ЛИМИТЫ СБРОШЕНЫ!</b>\n\n"
    text += f"🔥 RARE: {info['rare']['current']}/{info['rare']['max']}\n"
    text += f"⚡ HIGH: {info['high']['current']}/{info['high']['max']}\n"
    text += f"📊 MEDIUM: {info['medium']['current']}/{info['medium']['max']}"
    
    await message.answer(text, parse_mode="HTML")


async def cmd_freestatus(message: types.Message):
    """Статус FREE системы: /freestatus"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    from database import (
        get_free_users, get_pro_users, get_pending_free_signals,
        get_daily_counts, get_signals_sent_today
    )
    from config import FREE_SIGNAL_DELAY
    
    free_users = await get_free_users()
    pro_users = await get_pro_users()
    pending = await get_pending_free_signals()
    counts = await get_daily_counts()
    signals_today = await get_signals_sent_today()
    
    text = "📊 <b>FREE SYSTEM STATUS</b>\n\n"
    text += f"👥 <b>Users:</b>\n"
    text += f"   PRO: {len(pro_users)}\n"
    text += f"   FREE: {len(free_users)}\n\n"
    
    text += f"📈 <b>Signals Today:</b>\n"
    text += f"   🔥 RARE: {counts.get('rare', 0)}\n"
    text += f"   ⚡ HIGH: {counts.get('high', 0)}\n"
    text += f"   📊 MEDIUM: {counts.get('medium', 0)}\n"
    text += f"   📭 FREE sent: {counts.get('free_sent', 0)}\n"
    text += f"   Total: {signals_today}\n\n"
    
    text += f"⏳ <b>Pending for FREE:</b> {len(pending) if pending else 0}\n"
    text += f"   (delay: {FREE_SIGNAL_DELAY // 60} min)\n\n"
    
    if pending:
        text += "<b>Pending signals:</b>\n"
        for sig in pending[:5]:
            text += f"   • {sig['pair']} {sig['side']} ({sig['signal_type']})\n"
    
    await message.answer(text, parse_mode="HTML")


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


# ==================== БЭКАП КОМАНДЫ ====================

async def cmd_backup(message: types.Message):
    """Команда /backup - создать бэкап пользователей"""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    
    await message.answer("⏳ Создаю бэкап...")
    
    try:
        backup_data = await export_users_backup()
        
        # Сохраняем в файл
        backup_json = json.dumps(backup_data, ensure_ascii=False, indent=2)
        
        # Отправляем как документ
        from io import BytesIO
        file = BytesIO(backup_json.encode('utf-8'))
        file.name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        caption = f"✅ <b>БЭКАП СОЗДАН</b>\n\n"
        caption += f"👥 Всего пользователей: {backup_data['total_users']}\n"
        caption += f"💎 Премиум: {backup_data['premium_users']}\n"
        caption += f"📅 Дата: {backup_data['exported_at'][:19]}\n\n"
        caption += "💾 Сохрани этот файл!"
        
        await message.answer_document(file, caption=caption, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Backup error: {e}")
        await message.answer(f"❌ Ошибка бэкапа: {e}")


async def cmd_restore(message: types.Message):
    """Команда /restore - подсказка по восстановлению"""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    
    text = "📥 <b>ВОССТАНОВЛЕНИЕ ИЗ БЭКАПА</b>\n\n"
    text += "Чтобы восстановить данные:\n\n"
    text += "1️⃣ Отправь файл бэкапа (backup_*.json)\n"
    text += "2️⃣ Бот автоматически импортирует данные\n\n"
    text += "⚠️ Существующие пользователи будут обновлены,\n"
    text += "новые — добавлены."
    
    await message.answer(text, parse_mode="HTML")


async def handle_backup_file(message: types.Message):
    """Обработка загруженного файла бэкапа"""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    
    if not message.document:
        return
    
    if not message.document.file_name.endswith('.json'):
        await message.answer("❌ Нужен JSON файл бэкапа")
        return
    
    await message.answer("⏳ Импортирую данные...")
    
    try:
        # Скачиваем файл
        file = await message.bot.get_file(message.document.file_id)
        file_content = await message.bot.download_file(file.file_path)
        
        # Парсим JSON
        backup_data = json.loads(file_content.read().decode('utf-8'))
        
        # Проверяем структуру
        if "users" not in backup_data:
            await message.answer("❌ Неверный формат бэкапа")
            return
        
        # Импортируем
        result = await import_users_backup(backup_data)
        
        text = f"✅ <b>БЭКАП ВОССТАНОВЛЕН</b>\n\n"
        text += f"📥 Импортировано новых: {result['imported']}\n"
        text += f"🔄 Обновлено существующих: {result['updated']}\n"
        text += f"❌ Ошибок: {result['errors']}"
        
        await message.answer(text, parse_mode="HTML")
        
    except json.JSONDecodeError:
        await message.answer("❌ Ошибка чтения JSON файла")
    except Exception as e:
        logger.error(f"Restore error: {e}")
        await message.answer(f"❌ Ошибка восстановления: {e}")


async def cmd_referrals(message: types.Message):
    """Команда /referrals - статистика рефералов"""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    
    from database import get_all_referral_stats
    stats = await get_all_referral_stats()
    
    if not stats:
        await message.answer("👥 Пока нет рефералов с балансом")
        return
    
    total_pending = sum(s["earnings"] for s in stats)
    
    text = "👥 <b>СТАТИСТИКА РЕФЕРАЛОВ</b>\n\n"
    text += f"💰 Всего к выплате: <b>${total_pending:.2f}</b>\n\n"
    
    for s in stats[:20]:  # Топ 20
        uname = f"@{s['username']}" if s.get('username') else f"ID: {s['user_id']}"
        text += f"👤 {uname} — ${s['earnings']:.2f}\n"
        text += f"   📊 Рефов: {s['total_referrals']} (💎 оплативших: {s['paid_referrals']})\n"
    
    if len(stats) > 20:
        text += f"\n... и ещё {len(stats) - 20}"
    
    text += "\n\n<b>Для выплаты:</b>\n"
    text += "<code>/payout USER_ID</code> — обнулить баланс после выплаты"
    
    await message.answer(text, parse_mode="HTML")


async def cmd_payout(message: types.Message):
    """Команда /payout USER_ID - обнулить баланс после выплаты"""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    
    try:
        parts = message.text.split()
        if len(parts) >= 2:
            target_id = int(parts[1])
            
            from database import reset_referral_balance
            old_balance = await reset_referral_balance(target_id)
            
            if old_balance > 0:
                text = f"✅ <b>ВЫПЛАТА ЗАФИКСИРОВАНА</b>\n\n"
                text += f"👤 User ID: <code>{target_id}</code>\n"
                text += f"💰 Выплачено: <b>${old_balance:.2f}</b>\n"
                text += f"📊 Новый баланс: $0.00"
            else:
                text = f"ℹ️ У пользователя {target_id} баланс уже $0.00"
            
            await message.answer(text, parse_mode="HTML")
        else:
            await message.answer("❌ Формат: /payout USER_ID\n\nПример: /payout 123456789")
    except ValueError:
        await message.answer("❌ Неверный формат ID")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


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
    dp.register_message_handler(cmd_addmanager, commands=["addmanager"])
    dp.register_message_handler(cmd_delmanager, commands=["delmanager"])
    dp.register_message_handler(cmd_addbalance, commands=["addbalance"])
    dp.register_message_handler(cmd_testsplit, commands=["testsplit"])
    dp.register_message_handler(cmd_broadcast, commands=["broadcast"])
    dp.register_message_handler(cmd_backup, commands=["backup"])
    dp.register_message_handler(cmd_restore, commands=["restore"])
    dp.register_message_handler(cmd_referrals, commands=["referrals"])
    dp.register_message_handler(cmd_payout, commands=["payout"])
    dp.register_message_handler(cmd_limits, commands=["limits"])
    dp.register_message_handler(cmd_resetlimits, commands=["resetlimits"])
    dp.register_message_handler(cmd_freestatus, commands=["freestatus"])
    dp.register_message_handler(cmd_cancel, commands=["cancel"])
    
    # Документы (для бэкапа)
    dp.register_message_handler(handle_backup_file, content_types=["document"])
    
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
        
        # Вывод рефералки - получение кошелька
        if user_id in withdraw_state and withdraw_state[user_id]:
            from database import get_referral_stats
            wallet = message.text.strip()
            
            # Проверяем что похоже на кошелёк
            if len(wallet) < 20:
                lang = await get_user_lang(user_id)
                text = "❌ Invalid wallet address" if lang == "en" else "❌ Неверный адрес кошелька"
                await message.answer(text)
                return
            
            stats = await get_referral_stats(user_id)
            earnings = stats["earnings"]
            username = message.from_user.username
            
            # Отправляем уведомление админам
            for admin_id in ADMIN_IDS:
                try:
                    uname = f"@{username}" if username else f"ID: {user_id}"
                    admin_text = f"💰 <b>ЗАПРОС НА ВЫВОД</b>\n\n"
                    admin_text += f"👤 Пользователь: {uname}\n"
                    admin_text += f"🆔 ID: <code>{user_id}</code>\n"
                    admin_text += f"💵 Сумма: <b>${earnings:.2f}</b>\n"
                    admin_text += f"💳 Кошелёк: <code>{wallet}</code>\n\n"
                    admin_text += f"После перевода: <code>/payout {user_id}</code>"
                    
                    await message.bot.send_message(admin_id, admin_text, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {e}")
            
            # Подтверждение пользователю
            withdraw_state.pop(user_id, None)
            lang = await get_user_lang(user_id)
            
            if lang == "en":
                text = "✅ <b>WITHDRAWAL REQUEST SENT</b>\n\n"
                text += f"Amount: ${earnings:.2f}\n"
                text += f"Wallet: {wallet}\n\n"
                text += "We will process your request within 24 hours."
            else:
                text = "✅ <b>ЗАЯВКА НА ВЫВОД ОТПРАВЛЕНА</b>\n\n"
                text += f"Сумма: ${earnings:.2f}\n"
                text += f"Кошелёк: {wallet}\n\n"
                text += "Мы обработаем заявку в течение 24 часов."
            
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("⬅️ Назад" if lang == "ru" else "⬅️ Back", callback_data="back_main"))
            
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
            logger.info(f"Withdrawal request: user={user_id}, amount=${earnings:.2f}, wallet={wallet}")
            return
        
        # Промокод
        handled = await handle_promo_code(message)
        if not handled:
            lang = await get_user_lang(message.from_user.id)
            paid = await is_paid(message.from_user.id)
            await show_main_menu(message, lang, paid, is_start=True)


# Алиас для совместимости
register_handlers = setup_handlers
