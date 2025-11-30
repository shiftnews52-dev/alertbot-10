"""
payment_handlers.py - Обработчики для платёжной системы
Добавь эти функции в свой handlers.py
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
        text = "💎 <b>Choose Your Plan</b>\n\n"
        text += "Get access to premium trading signals:\n"
        text += "• 3-5 quality signals per day\n"
        text += "• Multi-strategy analysis\n"
        text += "• Automatic TP/SL levels\n"
        text += "• Up to 10 coins\n"
        text += "• 24/7 monitoring\n\n"
        text += "🎯 <b>Available Plans:</b>\n\n"
    else:
        text = "💎 <b>Выбери тарифный план</b>\n\n"
        text += "Получи доступ к премиум сигналам:\n"
        text += "• 3-5 качественных сигналов в день\n"
        text += "• Мультистратегия анализа\n"
        text += "• Автоматические TP/SL уровни\n"
        text += "• До 10 монет\n"
        text += "• Мониторинг 24/7\n\n"
        text += "🎯 <b>Доступные планы:</b>\n\n"
    
    # Планы
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        emoji = plan["emoji"]
        name = plan["name_en"] if lang == "en" else plan["name"]
        price = plan["price"]
        
        text += f"{emoji} <b>{name}</b> - ${price:.2f}\n"
        
        # Показываем скидку для планов > 1 месяца
        if plan_id != "1m":
            discount = calculate_discount(plan_id)
            if lang == "en":
                text += f"   💰 Save ${discount['discount_amount']:.0f} "
                text += f"({discount['discount_percent']}% off)\n"
                text += f"   📊 ${price/discount['months']:.2f}/month\n"
            else:
                text += f"   💰 Экономия ${discount['discount_amount']:.0f} "
                text += f"({discount['discount_percent']}% скидка)\n"
                text += f"   📊 ${price/discount['months']:.2f}/месяц\n"
        else:
            text += f"   📊 ${price:.2f}/месяц\n"
        
        text += "\n"
    
    if lang == "en":
        text += "\n💳 <b>Payment:</b> Crypto (USDT, TON, BTC, ETH)\n"
        text += "🔒 <b>Secure:</b> Powered by @CryptoBot\n\n"
        text += "Choose your plan below:"
    else:
        text += "\n💳 <b>Оплата:</b> Крипто (USDT, TON, BTC, ETH)\n"
        text += "🔒 <b>Безопасно:</b> Через @CryptoBot\n\n"
        text += "Выбери тариф ниже:"
    
    # Кнопки
    kb = InlineKeyboardMarkup(row_width=2)
    
    # План на 1 месяц
    plan = SUBSCRIPTION_PLANS["1m"]
    if lang == "en":
        btn_text = f"{plan['emoji']} {plan['name_en']} - ${plan['price']:.0f}"
    else:
        btn_text = f"{plan['emoji']} {plan['name']} - ${plan['price']:.0f}"
    kb.add(InlineKeyboardButton(btn_text, callback_data="pay_1m"))
    
    # План на 3 месяца
    plan = SUBSCRIPTION_PLANS["3m"]
    if lang == "en":
        btn_text = f"{plan['badge']} {plan['name_en']} - ${plan['price']:.0f}"
    else:
        btn_text = f"{plan['badge']} {plan['name']} - ${plan['price']:.0f}"
    kb.add(InlineKeyboardButton(btn_text, callback_data="pay_3m"))
    
    # План на 6 месяцев
    plan = SUBSCRIPTION_PLANS["6m"]
    if lang == "en":
        btn_text = f"{plan['badge']} {plan['name_en']} - ${plan['price']:.0f}"
    else:
        btn_text = f"{plan['badge']} {plan['name']} - ${plan['price']:.0f}"
    kb.add(InlineKeyboardButton(btn_text, callback_data="pay_6m"))
    
    # План на 12 месяцев (на всю ширину)
    plan = SUBSCRIPTION_PLANS["12m"]
    if lang == "en":
        btn_text = f"{plan['badge']} {plan['name_en']} - ${plan['price']:.0f}"
    else:
        btn_text = f"{plan['badge']} {plan['name']} - ${plan['price']:.0f}"
    kb.add(InlineKeyboardButton(btn_text, callback_data="pay_12m"))
    
    # Кнопка назад
    back_text = "⬅️ Back" if lang == "en" else "⬅️ Назад"
    kb.add(InlineKeyboardButton(back_text, callback_data="back_main"))
    
    # Отправляем
    if is_callback:
        try:
            await message.edit_text(text, reply_markup=kb)
        except:
            await message.answer(text, reply_markup=kb)
        await message_or_call.answer()
    else:
        await message.answer(text, reply_markup=kb)

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
        await call.message.edit_text(text, reply_markup=kb)
    except:
        await call.message.answer(text, reply_markup=kb)
    
    await call.answer()

# ==================== ПРОВЕРКА ОПЛАТЫ ====================
async def handle_payment_check(call: types.CallbackQuery):
    """Проверить статус оплаты"""
    user_id = call.from_user.id
    lang = await get_user_lang(user_id)
    
    # Парсим invoice_id из callback_data (check_12345 -> 12345)
    invoice_id = int(call.data.split("_")[1])
    
    # Проверяем статус
    status = await check_payment_status(invoice_id)
    
    if status == "paid":
        # Оплачено!
        text = "✅ <b>Payment Confirmed!</b>\n\n" if lang == "en" else "✅ <b>Оплата подтверждена!</b>\n\n"
        text += "Access activated! Use /start" if lang == "en" else "Доступ активирован! Используй /start"
        
        await call.message.edit_text(text)
        await call.answer("✅ Paid!" if lang == "en" else "✅ Оплачено!", show_alert=True)
    elif status == "active":
        # Ещё не оплачено
        text = "⏳ Payment not received yet.\n\nPlease complete the payment." if lang == "en" else "⏳ Оплата ещё не получена.\n\nПожалуйста, завершите оплату."
        await call.answer(text, show_alert=True)
    else:
        # Ошибка или expired
        text = "❌ Invoice expired or error.\n\nCreate new payment." if lang == "en" else "❌ Инвойс истёк или ошибка.\n\nСоздайте новый платёж."
        await call.answer(text, show_alert=True)

# ==================== ИНТЕГРАЦИЯ В setup_handlers ====================
"""
Добавь в функцию setup_handlers в handlers.py:

    # Меню оплаты
    @dp.callback_query_handler(lambda c: c.data == "menu_pay")
    async def menu_pay(call: types.CallbackQuery):
        await show_payment_menu(call, is_callback=True)
    
    # Выбор тарифного плана
    @dp.callback_query_handler(lambda c: c.data.startswith("pay_"))
    async def select_plan(call: types.CallbackQuery):
        await handle_plan_selection(call)
    
    # Проверка оплаты
    @dp.callback_query_handler(lambda c: c.data.startswith("check_"))
    async def check_payment(call: types.CallbackQuery):
        await handle_payment_check(call)
"""

# ==================== ВЕБХУК РОУТ (ДЛЯ RENDER) ====================
"""
Если используешь Render, добавь вебхук эндпоинт в main.py:

from aiohttp import web
from crypto_payment import handle_crypto_webhook

async def crypto_webhook_handler(request):
    '''Обработчик вебхуков от Crypto Bot'''
    signature = request.headers.get("Crypto-Pay-API-Signature", "")
    body = await request.read()
    
    success = await handle_crypto_webhook(signature, body)
    
    if success:
        return web.Response(text="OK")
    else:
        return web.Response(text="ERROR", status=400)

# В on_startup добавь:
app = web.Application()
app.router.add_post("/crypto_webhook", crypto_webhook_handler)
runner = web.AppRunner(app)
await runner.setup()
site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
await site.start()

# Настрой вебхук в Crypto Bot:
# https://pay.crypt.bot/api/setWebhook
# URL: https://your-render-app.onrender.com/crypto_webhook
"""
