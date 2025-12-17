"""
payment_handlers.py - Обработчики для платёжной системы
ОБНОВЛЁННЫЕ ТЕКСТЫ
"""
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from crypto_payment import (
    SUBSCRIPTION_PLANS, 
    create_payment_invoice,
    calculate_discount,
    check_payment_status
)
from database import get_user_lang, is_paid
import logging

logger = logging.getLogger(__name__)

# ==================== МЕНЮ ОПЛАТЫ ====================
async def show_payment_menu(message_or_call, is_callback=False):
    """Показать меню выбора тарифного плана"""
    if is_callback:
        user_id = message_or_call.from_user.id
        lang = await get_user_lang(user_id)
        message = message_or_call.message
    else:
        user_id = message_or_call.from_user.id
        lang = await get_user_lang(user_id)
        message = message_or_call
    
    # Заголовок
    if lang == "en":
        text = "🚀 <b>PREMIUM SIGNALS</b>\n\n"
        text += "You get not just signals, but a ready trading plan 👇\n\n"
        text += "✅ 3–5 quality signals per day\n"
        text += "✅ Multi-strategy (trend / corrections / impulse)\n"
        text += "✅ Clear entry, TP and SL levels\n"
        text += "✅ Up to 10 liquid coins\n"
        text += "✅ 24/7 market monitoring\n\n"
        text += "💡 Signals suit both beginners and experienced traders.\n\n"
        text += "📊 <b>AVAILABLE PLANS:</b>\n\n"
        text += "🗓 <b>1 month — $20</b>\n"
        text += "→ $20 / month\n\n"
        text += "🗓 <b>3 months — $50</b>\n"
        text += "💰 Save $10 (–17%)\n"
        text += "→ $16.67 / month\n\n"
        text += "🗓 <b>6 months — $90</b>\n"
        text += "💰 Save $30 (–25%)\n"
        text += "→ $15 / month\n\n"
        text += "👑 <b>12 months — $140</b> (TOP CHOICE)\n"
        text += "🔥 Save $100 (–42%)\n"
        text += "→ only $11.67 / month\n\n"
        text += "👉 The longer the subscription — the lower the price per signal."
    else:
        text = "🚀 <b>ПРЕМИУМ СИГНАЛЫ</b>\n\n"
        text += "Ты получаешь не просто сигналы, а готовый торговый план 👇\n\n"
        text += "✅ 3–5 качественных сигналов в день\n"
        text += "✅ Мультистратегия (тренд / коррекции / импульс)\n"
        text += "✅ Чёткие уровни входа, TP и SL\n"
        text += "✅ До 10 ликвидных монет\n"
        text += "✅ Круглосуточный мониторинг рынка 24/7\n\n"
        text += "💡 Сигналы подходят как для новичков, так и для опытных трейдеров.\n\n"
        text += "📊 <b>ДОСТУПНЫЕ ТАРИФЫ:</b>\n\n"
        text += "🗓 <b>1 месяц — $20</b>\n"
        text += "→ $20 / месяц\n\n"
        text += "🗓 <b>3 месяца — $50</b>\n"
        text += "💰 Экономия $10 (–17%)\n"
        text += "→ $16.67 / месяц\n\n"
        text += "🗓 <b>6 месяцев — $90</b>\n"
        text += "💰 Экономия $30 (–25%)\n"
        text += "→ $15 / месяц\n\n"
        text += "👑 <b>12 месяцев — $140</b> (ТОП ВЫБОР)\n"
        text += "🔥 Экономия $100 (–42%)\n"
        text += "→ всего $11.67 / месяц\n\n"
        text += "👉 Чем дольше подписка — тем ниже цена одного сигнала."
    
    # Кнопки
    kb = InlineKeyboardMarkup(row_width=1)
    
    if lang == "en":
        kb.add(InlineKeyboardButton("🗓 1 month — $20", callback_data="pay_1m"))
        kb.add(InlineKeyboardButton("🗓 3 months — $50 (–17%)", callback_data="pay_3m"))
        kb.add(InlineKeyboardButton("🗓 6 months — $90 (–25%)", callback_data="pay_6m"))
        kb.add(InlineKeyboardButton("👑 12 months — $140 (–42%)", callback_data="pay_12m"))
        kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back_main"))
    else:
        kb.add(InlineKeyboardButton("🗓 1 месяц — $20", callback_data="pay_1m"))
        kb.add(InlineKeyboardButton("🗓 3 месяца — $50 (–17%)", callback_data="pay_3m"))
        kb.add(InlineKeyboardButton("🗓 6 месяцев — $90 (–25%)", callback_data="pay_6m"))
        kb.add(InlineKeyboardButton("👑 12 месяцев — $140 (–42%)", callback_data="pay_12m"))
        kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_main"))
    
    # Отправляем
    if is_callback:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
        await message_or_call.answer()
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ==================== МЕНЮ ПРОДЛЕНИЯ СО СКИДКОЙ 25% ====================
async def show_renewal_menu(message_or_call, is_callback=False):
    """Показать меню продления со скидкой 25%"""
    if is_callback:
        user_id = message_or_call.from_user.id
        lang = await get_user_lang(user_id)
        message = message_or_call.message
    else:
        user_id = message_or_call.from_user.id
        lang = await get_user_lang(user_id)
        message = message_or_call
    
    # Цены со скидкой 25%
    prices = {
        "1m": {"original": 20, "discounted": 15},
        "3m": {"original": 50, "discounted": 37.5},
        "6m": {"original": 90, "discounted": 67.5},
        "12m": {"original": 140, "discounted": 105},
    }
    
    if lang == "en":
        text = "🎁 <b>SPECIAL RENEWAL OFFER!</b>\n\n"
        text += "You get <b>25% OFF</b> on any plan 🔥\n\n"
        text += "📊 <b>DISCOUNTED PRICES:</b>\n\n"
        text += f"🗓 <b>1 month</b>\n"
        text += f"   <s>${prices['1m']['original']}</s> → <b>${prices['1m']['discounted']:.0f}</b>\n\n"
        text += f"🗓 <b>3 months</b>\n"
        text += f"   <s>${prices['3m']['original']}</s> → <b>${prices['3m']['discounted']:.1f}</b>\n\n"
        text += f"🗓 <b>6 months</b>\n"
        text += f"   <s>${prices['6m']['original']}</s> → <b>${prices['6m']['discounted']:.1f}</b>\n\n"
        text += f"👑 <b>12 months</b>\n"
        text += f"   <s>${prices['12m']['original']}</s> → <b>${prices['12m']['discounted']:.0f}</b>\n\n"
        text += "⏰ <i>Limited time offer!</i>"
    else:
        text = "🎁 <b>СПЕЦИАЛЬНОЕ ПРЕДЛОЖЕНИЕ!</b>\n\n"
        text += "Скидка <b>25%</b> на любой тариф 🔥\n\n"
        text += "📊 <b>ЦЕНЫ СО СКИДКОЙ:</b>\n\n"
        text += f"🗓 <b>1 месяц</b>\n"
        text += f"   <s>${prices['1m']['original']}</s> → <b>${prices['1m']['discounted']:.0f}</b>\n\n"
        text += f"🗓 <b>3 месяца</b>\n"
        text += f"   <s>${prices['3m']['original']}</s> → <b>${prices['3m']['discounted']:.1f}</b>\n\n"
        text += f"🗓 <b>6 месяцев</b>\n"
        text += f"   <s>${prices['6m']['original']}</s> → <b>${prices['6m']['discounted']:.1f}</b>\n\n"
        text += f"👑 <b>12 месяцев</b>\n"
        text += f"   <s>${prices['12m']['original']}</s> → <b>${prices['12m']['discounted']:.0f}</b>\n\n"
        text += "⏰ <i>Предложение ограничено!</i>"
    
    # Кнопки со скидкой
    kb = InlineKeyboardMarkup(row_width=1)
    
    if lang == "en":
        kb.add(InlineKeyboardButton(f"🗓 1 month — ${prices['1m']['discounted']:.0f}", callback_data="renew_1m"))
        kb.add(InlineKeyboardButton(f"🗓 3 months — ${prices['3m']['discounted']:.1f}", callback_data="renew_3m"))
        kb.add(InlineKeyboardButton(f"🗓 6 months — ${prices['6m']['discounted']:.1f}", callback_data="renew_6m"))
        kb.add(InlineKeyboardButton(f"👑 12 months — ${prices['12m']['discounted']:.0f}", callback_data="renew_12m"))
        kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back_main"))
    else:
        kb.add(InlineKeyboardButton(f"🗓 1 месяц — ${prices['1m']['discounted']:.0f}", callback_data="renew_1m"))
        kb.add(InlineKeyboardButton(f"🗓 3 месяца — ${prices['3m']['discounted']:.1f}", callback_data="renew_3m"))
        kb.add(InlineKeyboardButton(f"🗓 6 месяцев — ${prices['6m']['discounted']:.1f}", callback_data="renew_6m"))
        kb.add(InlineKeyboardButton(f"👑 12 месяцев — ${prices['12m']['discounted']:.0f}", callback_data="renew_12m"))
        kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_main"))
    
    # Отправляем
    if is_callback:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
        await message_or_call.answer()
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ==================== ОБРАБОТКА ВЫБОРА ПЛАНА ====================
async def handle_plan_selection(call: types.CallbackQuery):
    """Обработка выбора тарифного плана"""
    user_id = call.from_user.id
    lang = await get_user_lang(user_id)
    
    # Парсим plan_id из callback_data (pay_1m -> 1m)
    plan_id = call.data.split("_")[1]
    
    # Создаём инвойс
    invoice = await create_payment_invoice(user_id, plan_id, lang)
    
    if not invoice:
        error_text = "❌ Payment error. Try again later." if lang == "en" else "❌ Ошибка создания платежа. Попробуй позже."
        await call.answer(error_text, show_alert=True)
        return
    
    plan = invoice["plan"]
    pay_url = invoice["pay_url"]
    
    # Формируем сообщение
    if lang == "en":
        text = f"💎 <b>Payment Details</b>\n\n"
        text += f"📦 Plan: {plan['name_en']}\n"
        text += f"💰 Price: ${plan['price']:.2f}\n"
        text += f"⏱ Duration: {plan['duration_days']} days\n\n"
        
        if plan_id != "1m":
            discount = calculate_discount(plan_id)
            text += f"🎁 You save: ${discount['discount_amount']:.0f} "
            text += f"({discount['discount_percent']}% discount)\n\n"
        
        text += f"💳 <b>Payment methods:</b>\n"
        text += f"USDT • TON • BTC • ETH • and more\n\n"
        text += f"🔒 Secure payment via @CryptoBot\n\n"
        text += f"Click the button below to pay:"
    else:
        text = f"💎 <b>Детали оплаты</b>\n\n"
        text += f"📦 Тариф: {plan['name']}\n"
        text += f"💰 Цена: ${plan['price']:.2f}\n"
        text += f"⏱ Длительность: {plan['duration_days']} дней\n\n"
        
        if plan_id != "1m":
            discount = calculate_discount(plan_id)
            text += f"🎁 Экономия: ${discount['discount_amount']:.0f} "
            text += f"({discount['discount_percent']}% скидка)\n\n"
        
        text += f"💳 <b>Способы оплаты:</b>\n"
        text += f"USDT • TON • BTC • ETH • и другие\n\n"
        text += f"🔒 Безопасная оплата через @CryptoBot\n\n"
        text += f"Нажми кнопку ниже для оплаты:"
    
    # Кнопки
    kb = InlineKeyboardMarkup()
    pay_btn_text = "💳 Pay Now" if lang == "en" else "💳 Оплатить"
    kb.add(InlineKeyboardButton(pay_btn_text, url=pay_url))
    
    check_btn_text = "✅ I Paid" if lang == "en" else "✅ Я оплатил"
    kb.add(InlineKeyboardButton(check_btn_text, callback_data=f"check_{invoice['invoice_id']}"))
    
    back_text = "⬅️ Back" if lang == "en" else "⬅️ Назад"
    kb.add(InlineKeyboardButton(back_text, callback_data="menu_pay"))
    
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    
    await call.answer()


# ==================== ПРОВЕРКА ОПЛАТЫ ====================
async def handle_payment_check(call: types.CallbackQuery):
    """Проверить статус оплаты"""
    from database import grant_access, get_referrer, add_referral_bonus
    
    user_id = call.from_user.id
    lang = await get_user_lang(user_id)
    
    # Парсим invoice_id из callback_data (check_12345 -> 12345)
    invoice_id = int(call.data.split("_")[1])
    
    # Проверяем статус
    status, payload = await check_payment_status(invoice_id)
    
    logger.info(f"Payment check: user={user_id}, invoice={invoice_id}, status={status}, payload={payload}")
    
    if status == "paid":
        # Оплачено! Парсим payload для получения plan_id
        plan_id = "1m"  # default
        price = 20.0    # default
        days = 30       # default
        
        try:
            # payload формат: "user_id:plan_id"
            if payload and ":" in payload:
                _, plan_id = payload.split(":")
                plan = SUBSCRIPTION_PLANS.get(plan_id)
                if plan:
                    days = plan["duration_days"]
                    price = plan["price"]
            
            # ВЫДАЁМ ДОСТУП!
            await grant_access(user_id, days)
            logger.info(f"✅ Access granted: user={user_id}, days={days}")
            
            # НАЧИСЛЯЕМ РЕФЕРАЛЬНЫЙ БОНУС ($10 за приглашённого)
            referrer_id = await get_referrer(user_id)
            if referrer_id:
                bonus = 10.0  # Фиксированные $10 за приглашённого
                await add_referral_bonus(referrer_id, bonus, user_id)
                logger.info(f"💰 Referral bonus: {referrer_id} got ${bonus:.2f} from {user_id}")
            
        except Exception as e:
            logger.error(f"Error granting access: {e}")
            # Всё равно выдаём 30 дней как fallback
            await grant_access(user_id, 30)
        
        if lang == "en":
            text = "✅ <b>Payment Confirmed!</b>\n\n"
            text += "Premium access activated!\n"
            text += "Now follow signals and manage risk.\n\n"
            text += "Use /start to open menu"
        else:
            text = "✅ <b>Оплата подтверждена!</b>\n\n"
            text += "Премиум-доступ активирован!\n"
            text += "Теперь следуй сигналам и управляй риском.\n\n"
            text += "Используй /start чтобы открыть меню"
        
        await call.message.edit_text(text, parse_mode="HTML")
        await call.answer("✅ Paid!" if lang == "en" else "✅ Оплачено!", show_alert=True)
    elif status == "active":
        # Ещё не оплачено
        text = "⏳ Payment not received yet.\n\nPlease complete the payment." if lang == "en" else "⏳ Оплата ещё не получена.\n\nПожалуйста, завершите оплату."
        await call.answer(text, show_alert=True)
    else:
        # Ошибка или expired
        text = "❌ Invoice expired or error.\n\nCreate new payment." if lang == "en" else "❌ Инвойс истёк или ошибка.\n\nСоздайте новый платёж."
        await call.answer(text, show_alert=True)


# ==================== ОБРАБОТКА ПРОДЛЕНИЯ СО СКИДКОЙ ====================
async def handle_renewal_selection(call: types.CallbackQuery):
    """Обработка выбора плана со скидкой 25%"""
    from config import RENEWAL_DISCOUNT_PERCENT
    
    user_id = call.from_user.id
    lang = await get_user_lang(user_id)
    
    # Парсим plan_id из callback_data (renew_1m -> 1m)
    plan_id = call.data.split("_")[1]
    
    # Создаём инвойс со скидкой
    invoice = await create_payment_invoice(user_id, plan_id, lang, discount_percent=RENEWAL_DISCOUNT_PERCENT)
    
    if not invoice:
        error_text = "❌ Payment error. Try again later." if lang == "en" else "❌ Ошибка создания платежа. Попробуй позже."
        await call.answer(error_text, show_alert=True)
        return
    
    plan = invoice["plan"]
    pay_url = invoice["pay_url"]
    final_price = invoice.get("final_price", plan["price"])
    original_price = plan["price"]
    
    # Формируем сообщение
    if lang == "en":
        text = f"🎁 <b>RENEWAL WITH DISCOUNT</b>\n\n"
        text += f"📦 Plan: {plan['name_en']}\n"
        text += f"💰 Original: <s>${original_price:.2f}</s>\n"
        text += f"🔥 Your price: <b>${final_price:.2f}</b>\n"
        text += f"💎 You save: ${original_price - final_price:.2f} ({RENEWAL_DISCOUNT_PERCENT}%)\n"
        text += f"⏱ Duration: {plan['duration_days']} days\n\n"
        text += f"💳 <b>Payment methods:</b>\n"
        text += f"USDT • TON • BTC • ETH • and more\n\n"
        text += f"🔒 Secure payment via @CryptoBot\n\n"
        text += f"Click the button below to pay:"
    else:
        text = f"🎁 <b>ПРОДЛЕНИЕ СО СКИДКОЙ</b>\n\n"
        text += f"📦 Тариф: {plan['name']}\n"
        text += f"💰 Было: <s>${original_price:.2f}</s>\n"
        text += f"🔥 Твоя цена: <b>${final_price:.2f}</b>\n"
        text += f"💎 Экономия: ${original_price - final_price:.2f} ({RENEWAL_DISCOUNT_PERCENT}%)\n"
        text += f"⏱ Длительность: {plan['duration_days']} дней\n\n"
        text += f"💳 <b>Способы оплаты:</b>\n"
        text += f"USDT • TON • BTC • ETH • и другие\n\n"
        text += f"🔒 Безопасная оплата через @CryptoBot\n\n"
        text += f"Нажми кнопку ниже для оплаты:"
    
    # Кнопки
    kb = InlineKeyboardMarkup()
    pay_btn_text = "💳 Pay Now" if lang == "en" else "💳 Оплатить"
    kb.add(InlineKeyboardButton(pay_btn_text, url=pay_url))
    
    check_btn_text = "✅ I Paid" if lang == "en" else "✅ Я оплатил"
    kb.add(InlineKeyboardButton(check_btn_text, callback_data=f"check_{invoice['invoice_id']}_{plan_id}"))
    
    back_text = "⬅️ Back" if lang == "en" else "⬅️ Назад"
    kb.add(InlineKeyboardButton(back_text, callback_data="renew_discount"))
    
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()
