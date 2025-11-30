"""
tasks.py - Фоновые задачи (УПРОЩЁННАЯ ВЕРСИЯ)
"""
import time
import asyncio
import logging
from collections import defaultdict
import httpx
from aiogram import Bot
from aiogram.utils.exceptions import RetryAfter, TelegramAPIError

from config import (
    CHECK_INTERVAL, DEFAULT_PAIRS, TIMEFRAMES,
    MAX_SIGNALS_PER_DAY, BATCH_SEND_SIZE, BATCH_SEND_DELAY
)
from database import (
    get_all_tracked_pairs, get_pairs_with_users,
    count_signals_today, log_signal
)
from indicators import CANDLES, fetch_price, analyze_signal, fetch_candles_binance

logger = logging.getLogger(__name__)
LAST_SIGNALS = {}

async def send_message_safe(bot: Bot, user_id: int, text: str, **kwargs):
    """Безопасная отправка с обработкой rate limit"""
    try:
        await bot.send_message(user_id, text, **kwargs)
        return True
    except RetryAfter as e:
        await asyncio.sleep(e.timeout)
        return await send_message_safe(bot, user_id, text, **kwargs)
    except TelegramAPIError:
        return False

async def price_collector(bot: Bot):
    """Сбор рыночных данных"""
    logger.info("🔄 Price Collector started")
    
    # Сначала загружаем исторические данные
    logger.info("📥 Loading historical data...")
    for pair in DEFAULT_PAIRS:
        for tf in TIMEFRAMES:
            try:
                candles = await fetch_candles_binance(pair, tf, 100)
                if candles:
                    for candle in candles:
                        CANDLES.add_candle(pair, tf, candle)
                    logger.info(f"✅ Loaded {len(candles)} candles for {pair} {tf}")
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Error loading {pair} {tf}: {e}")
    
    logger.info("✅ Historical data loaded!")
    
    # Затем регулярный сбор
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # Собираем текущие цены
                pairs = await get_all_tracked_pairs()
                pairs = list(set(pairs + DEFAULT_PAIRS))
                
                ts = time.time()
                for pair in pairs:
                    price_data = await fetch_price(client, pair)
                    if price_data:
                        price, volume = price_data
                        # Добавляем в свечи
                        CANDLES.add_candle(pair, "1h", {
                            't': ts, 'o': price, 'h': price, 
                            'l': price, 'c': price, 'v': volume
                        })
                
                logger.info(f"📊 Prices updated for {len(pairs)} pairs")
                await asyncio.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Price collector error: {e}")
                await asyncio.sleep(60)

async def signal_analyzer(bot: Bot):
    """Анализ и отправка сигналов"""
    logger.info("🎯 Signal Analyzer started")
    
    # Ждём загрузки данных
    await asyncio.sleep(10)
    
    while True:
        try:
            rows = await get_pairs_with_users()
            
            # Группируем по парам
            pairs_users = defaultdict(list)
            for row in rows:
                pairs_users[row["pair"]].append(row["user_id"])
            
            # Анализируем каждую пару
            now = time.time()
            for pair, users in pairs_users.items():
                # Проверка лимита
                signals_today = await count_signals_today(pair)
                if signals_today >= MAX_SIGNALS_PER_DAY:
                    continue
                
                # Cooldown
                key = pair
                if now - LAST_SIGNALS.get(key, 0) < 3600:
                    continue
                
                # Анализ
                signal = analyze_signal(pair)
                if not signal:
                    continue
                
                # Формируем сообщение
                side_emoji = "🟢" if signal['side'] == 'LONG' else "🔴"
                
                text = f"{side_emoji} <b>{signal['pair']} — {signal['side']}</b>\n\n"
                text += "<b>Логика:</b>\n"
                for reason in signal['reasons']:
                    text += f"• {reason}\n"
                text += "\n"
                
                entry_min, entry_max = signal['entry_zone']
                text += f"🎯 <b>Вход:</b> {entry_min:.2f} – {entry_max:.2f}\n"
                text += f"🎯 <b>Цели:</b>\n"
                text += f"   TP1: {signal['take_profit_1']:.2f} (+{signal['tp1_percent']:.2f}%)\n"
                text += f"   TP2: {signal['take_profit_2']:.2f} (+{signal['tp2_percent']:.2f}%)\n"
                text += f"   TP3: {signal['take_profit_3']:.2f} (+{signal['tp3_percent']:.2f}%)\n"
                text += f"🛡 <b>Стоп:</b> {signal['stop_loss']:.2f} (-{signal['sl_percent']:.2f}%)\n\n"
                text += f"💰 <b>Объём:</b> {signal['position_size']}\n"
                text += f"📊 <b>Confidence:</b> {signal['confidence']}%\n\n"
                text += "⏰ " + time.strftime('%H:%M:%S') + "\n"
                text += "⚠️ <i>Не финансовый совет</i>"
                
                # Отправка
                sent_count = 0
                for user_id in users:
                    if await send_message_safe(bot, user_id, text):
                        await log_signal(user_id, pair, signal['side'], signal['price'], signal['confidence'])
                        sent_count += 1
                    await asyncio.sleep(0.05)
                
                LAST_SIGNALS[key] = now
                logger.info(f"🎯 Signal: {pair} {signal['side']} to {sent_count} users")
                
        except Exception as e:
            logger.error(f"Signal analyzer error: {e}")
        
        await asyncio.sleep(60)
