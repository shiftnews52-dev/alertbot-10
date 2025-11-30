"""
pnl_handlers.py - Обработчики команд для статистики PnL
Добавь эти функции в handlers.py
"""

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pnl_tracker import pnl_tracker
from database import get_user_lang
from config import t

# ==================== КОМАНДА /stats ====================
async def cmd_stats(message: types.Message):
    """Показать статистику за последние 30 дней"""
    lang = await get_user_lang(message.from_user.id)
    
    # Получить статистику
    stats = await pnl_tracker.get_statistics(days=30)
    
    # Формируем красивое сообщение
    text = "📊 <b>СТАТИСТИКА (30 ДНЕЙ)</b>\n\n"
    
    # Общая информация
    text += f"🔔 <b>Всего сигналов:</b> {stats['total_signals']}\n"
    text += f"✅ Закрыто: {stats['closed_signals']}\n"
    text += f"⏳ Активных: {stats['active_signals']}\n\n"
    
    if stats['closed_signals'] > 0:
        # Винрейт
        winrate_emoji = "🟢" if stats['winrate'] >= 70 else "🟡" if stats['winrate'] >= 60 else "🔴"
        text += f"{winrate_emoji} <b>Винрейт:</b> {stats['winrate']:.1f}%\n\n"
        
        # PnL
        total_pnl_emoji = "💰" if stats['total_pnl'] > 0 else "📉"
        text += f"{total_pnl_emoji} <b>Общий PnL:</b> {stats['total_pnl']:+.2f}%\n"
        text += f"📈 Средняя прибыль: +{stats['avg_win']:.2f}%\n"
        text += f"📉 Средний убыток: {stats['avg_loss']:.2f}%\n\n"
        
        # Лучший/худший
        text += f"🏆 Лучшая сделка: +{stats['best_trade']:.2f}%\n"
        text += f"💔 Худшая сделка: {stats['worst_trade']:.2f}%\n\n"
        
        # Распределение результатов
        text += f"<b>📊 Результаты:</b>\n"
        text += f"🎯 TP1: {stats['tp1_count']}\n"
        text += f"🎯 TP2: {stats['tp2_count']}\n"
        text += f"🎯 TP3: {stats['tp3_count']}\n"
        text += f"🛡 SL: {stats['sl_count']}\n\n"
        
        # Средняя продолжительность
        hours = int(stats['avg_duration_hours'])
        minutes = int((stats['avg_duration_hours'] - hours) * 60)
        text += f"⏱ Средняя продолжительность: {hours}ч {minutes}м\n"
    else:
        text += "⏳ <i>Пока нет закрытых сигналов...</i>\n"
        text += "Получи первый сигнал и начинай зарабатывать! 💰"
    
    # Кнопки для разных периодов
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("7 дней", callback_data="stats_7"),
        InlineKeyboardButton("30 дней", callback_data="stats_30"),
        InlineKeyboardButton("90 дней", callback_data="stats_90")
    )
    kb.add(InlineKeyboardButton("📊 По парам", callback_data="stats_pairs"))
    kb.add(InlineKeyboardButton(t(lang, "btn_back"), callback_data="back_main"))
    
    await message.answer(text, reply_markup=kb)

# ==================== CALLBACK ОБРАБОТЧИКИ ====================
async def stats_period_callback(call: types.CallbackQuery):
    """Обработчик выбора периода статистики"""
    lang = await get_user_lang(call.from_user.id)
    
    # Парсим период
    period = int(call.data.split("_")[1])
    
    # Получить статистику
    stats = await pnl_tracker.get_statistics(days=period)
    
    # Формируем сообщение (аналогично cmd_stats)
    period_text = "7 дней" if period == 7 else "30 дней" if period == 30 else "90 дней"
    text = f"📊 <b>СТАТИСТИКА ({period_text.upper()})</b>\n\n"
    
    text += f"🔔 <b>Всего сигналов:</b> {stats['total_signals']}\n"
    text += f"✅ Закрыто: {stats['closed_signals']}\n"
    text += f"⏳ Активных: {stats['active_signals']}\n\n"
    
    if stats['closed_signals'] > 0:
        winrate_emoji = "🟢" if stats['winrate'] >= 70 else "🟡" if stats['winrate'] >= 60 else "🔴"
        text += f"{winrate_emoji} <b>Винрейт:</b> {stats['winrate']:.1f}%\n\n"
        
        total_pnl_emoji = "💰" if stats['total_pnl'] > 0 else "📉"
        text += f"{total_pnl_emoji} <b>Общий PnL:</b> {stats['total_pnl']:+.2f}%\n"
        text += f"📈 Средняя прибыль: +{stats['avg_win']:.2f}%\n"
        text += f"📉 Средний убыток: {stats['avg_loss']:.2f}%\n\n"
        
        text += f"🏆 Лучшая сделка: +{stats['best_trade']:.2f}%\n"
        text += f"💔 Худшая сделка: {stats['worst_trade']:.2f}%\n\n"
        
        text += f"<b>📊 Результаты:</b>\n"
        text += f"🎯 TP1: {stats['tp1_count']}\n"
        text += f"🎯 TP2: {stats['tp2_count']}\n"
        text += f"🎯 TP3: {stats['tp3_count']}\n"
        text += f"🛡 SL: {stats['sl_count']}\n\n"
        
        hours = int(stats['avg_duration_hours'])
        minutes = int((stats['avg_duration_hours'] - hours) * 60)
        text += f"⏱ Средняя продолжительность: {hours}ч {minutes}м\n"
    else:
        text += "⏳ <i>Нет закрытых сигналов за этот период</i>\n"
    
    # Кнопки
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("7 дней", callback_data="stats_7"),
        InlineKeyboardButton("30 дней", callback_data="stats_30"),
        InlineKeyboardButton("90 дней", callback_data="stats_90")
    )
    kb.add(InlineKeyboardButton("📊 По парам", callback_data="stats_pairs"))
    kb.add(InlineKeyboardButton(t(lang, "btn_back"), callback_data="back_main"))
    
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except:
        await call.message.answer(text, reply_markup=kb)
    
    await call.answer()

async def stats_pairs_callback(call: types.CallbackQuery):
    """Показать статистику по парам"""
    lang = await get_user_lang(call.from_user.id)
    
    from config import DEFAULT_PAIRS
    
    text = "📊 <b>СТАТИСТИКА ПО ПАРАМ (30 ДНЕЙ)</b>\n\n"
    
    # Получить статистику по каждой паре
    pairs_stats = []
    for pair in DEFAULT_PAIRS:
        stats = await pnl_tracker.get_pair_statistics(pair, days=30)
        if stats['signals'] > 0:
            pairs_stats.append(stats)
    
    if pairs_stats:
        # Сортировать по винрейту
        pairs_stats.sort(key=lambda x: x['winrate'], reverse=True)
        
        for i, stats in enumerate(pairs_stats, 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📊"
            winrate_emoji = "🟢" if stats['winrate'] >= 70 else "🟡" if stats['winrate'] >= 60 else "🔴"
            pnl_emoji = "💰" if stats['total_pnl'] > 0 else "📉"
            
            text += f"{emoji} <b>{stats['pair']}</b>\n"
            text += f"   Сигналов: {stats['signals']}\n"
            text += f"   {winrate_emoji} Винрейт: {stats['winrate']:.1f}%\n"
            text += f"   {pnl_emoji} PnL: {stats['total_pnl']:+.2f}%\n\n"
    else:
        text += "⏳ <i>Нет данных по парам за этот период</i>\n"
    
    # Кнопки
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(t(lang, "btn_back"), callback_data="stats_30"))
    
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except:
        await call.message.answer(text, reply_markup=kb)
    
    await call.answer()

# ==================== АКТИВНЫЕ СИГНАЛЫ ====================
async def cmd_active(message: types.Message):
    """Показать активные сигналы"""
    lang = await get_user_lang(message.from_user.id)
    
    active = await pnl_tracker.get_active_signals()
    
    if not active:
        text = "⏳ <b>Нет активных сигналов</b>\n\n"
        text += "Ожидай следующий качественный сигнал! 🎯"
        await message.answer(text)
        return
    
    text = f"⏳ <b>АКТИВНЫЕ СИГНАЛЫ ({len(active)})</b>\n\n"
    
    for signal in active:
        pair = signal['pair']
        side = signal['side']
        entry = signal['entry_price']
        tp1 = signal['take_profit_1']
        tp2 = signal['take_profit_2']
        tp3 = signal['take_profit_3']
        sl = signal['stop_loss']
        
        # Эмодзи для направления
        emoji = "📈" if side == "LONG" else "📉"
        
        text += f"{emoji} <b>{pair}</b> {side}\n"
        text += f"   Вход: <code>{entry:.8f}</code>\n"
        
        # Отметки для достигнутых TP
        tp1_status = "✅" if signal['tp1_hit'] else "⏳"
        tp2_status = "✅" if signal['tp2_hit'] else "⏳"
        tp3_status = "✅" if signal['tp3_hit'] else "⏳"
        
        text += f"   {tp1_status} TP1: <code>{tp1:.8f}</code>\n"
        text += f"   {tp2_status} TP2: <code>{tp2:.8f}</code>\n"
        text += f"   {tp3_status} TP3: <code>{tp3:.8f}</code>\n"
        text += f"   🛡 SL: <code>{sl:.8f}</code>\n\n"
    
    await message.answer(text)

# ==================== ИНТЕГРАЦИЯ В setup_handlers ====================
"""
Добавь в функцию setup_handlers в handlers.py:

    # PnL команды
    @dp.message_handler(commands=["stats"])
    async def handle_stats(message: types.Message):
        await cmd_stats(message)
    
    @dp.message_handler(commands=["active"])
    async def handle_active(message: types.Message):
        await cmd_active(message)
    
    @dp.callback_query_handler(lambda c: c.data.startswith("stats_") and c.data.split("_")[1].isdigit())
    async def handle_stats_period(call: types.CallbackQuery):
        await stats_period_callback(call)
    
    @dp.callback_query_handler(lambda c: c.data == "stats_pairs")
    async def handle_stats_pairs(call: types.CallbackQuery):
        await stats_pairs_callback(call)
"""
