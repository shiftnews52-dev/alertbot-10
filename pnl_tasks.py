"""
pnl_tasks.py - Фоновые задачи для отслеживания PnL
"""
import asyncio
import logging
import httpx
from aiogram import Bot

from pnl_tracker import pnl_tracker
from indicators import fetch_price, PRICE_CACHE
from database import get_all_user_ids

logger = logging.getLogger(__name__)

async def track_signals_pnl(bot: Bot):
    """
    Фоновая задача для отслеживания активных сигналов
    Проверяет каждые 60 секунд достигли ли сигналы TP/SL
    """
    logger.info("PnL tracker task started")
    
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # Получить все активные сигналы
                active_signals = await pnl_tracker.get_active_signals()
                
                if not active_signals:
                    await asyncio.sleep(60)
                    continue
                
                # Проверить каждый сигнал
                for signal in active_signals:
                    pair = signal['pair']
                    signal_id = signal['id']
                    
                    # Получить текущую цену
                    price_data = await fetch_price(client, pair)
                    if not price_data:
                        continue
                    
                    current_price, _ = price_data
                    
                    # Проверить достигла ли цена TP/SL
                    result = await pnl_tracker.check_signal(signal_id, current_price)
                    
                    if result:
                        # Отправить уведомление пользователям
                        await notify_users_about_result(bot, signal, result)
                
                # Очистить старый кэш
                PRICE_CACHE.clear_old()
                
            except Exception as e:
                logger.error(f"PnL tracker error: {e}")
            
            await asyncio.sleep(60)  # Проверять каждую минуту

async def notify_users_about_result(bot: Bot, signal: dict, result: dict):
    """
    Отправить уведомление пользователям о закрытии сигнала
    
    Args:
        signal: данные сигнала из БД
        result: {'result': 'tp1/tp2/tp3/sl', 'pnl_percent': 2.5}
    """
    pair = signal['pair']
    side = signal['side']
    entry = signal['entry_price']
    pnl = result['pnl_percent']
    result_type = result['result']
    
    # Эмодзи для результата
    if 'tp' in result_type:
        emoji = "🎯"
        outcome = "TP" + result_type[-1] if result_type[-1].isdigit() else "TP"
        color = "green"
    else:
        emoji = "🛡"
        outcome = "SL"
        color = "red"
    
    # Формируем сообщение
    text = f"{emoji} <b>ЗАКРЫТИЕ СИГНАЛА</b>\n\n"
    text += f"<b>Монета:</b> {pair}\n"
    text += f"<b>Направление:</b> {side}\n"
    text += f"<b>Вход:</b> <code>{entry:.8f}</code>\n"
    text += f"<b>Результат:</b> {outcome}\n\n"
    
    if pnl > 0:
        text += f"💰 <b>Прибыль:</b> +{pnl:.2f}%\n"
    else:
        text += f"📉 <b>Убыток:</b> {pnl:.2f}%\n"
    
    # Рекомендации по управлению позицией
    if result_type == 'tp1_partial':
        text += f"\n💡 <b>Действие:</b> Закрой 15% позиции"
    elif result_type == 'tp2_partial':
        text += f"\n💡 <b>Действие:</b> Закрой 40% позиции, передвинь SL в безубыток"
    elif result_type == 'tp3':
        text += f"\n💡 <b>Действие:</b> Закрой 80% позиции, оставь 20% с трейлингом"
    elif result_type == 'sl':
        text += f"\n⚠️ Stop Loss сработал. Следующий раз повезёт!"
    
    # Отправить всем пользователям (можно оптимизировать - только тем кто следит за этой парой)
    user_ids = await get_all_user_ids()
    
    sent = 0
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, text)
            sent += 1
            await asyncio.sleep(0.05)  # Небольшая задержка
        except Exception as e:
            logger.debug(f"Failed to send PnL notification to {user_id}: {e}")
    
    logger.info(f"PnL notification sent to {sent} users: {pair} {result_type} {pnl:.2f}%")
