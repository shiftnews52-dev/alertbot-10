"""
tasks.py - Фоновые задачи с антиспамом и упрощённым форматом
"""
import time
import asyncio
import logging
from collections import defaultdict
import httpx
from aiogram import Bot
from aiogram.utils.exceptions import RetryAfter, TelegramAPIError

from config import (
    CHECK_INTERVAL, DEFAULT_PAIRS, TIMEFRAME,
    MAX_SIGNALS_PER_DAY, BATCH_SEND_SIZE, BATCH_SEND_DELAY,
    SIGNAL_COOLDOWN, MIN_CONFIDENCE_SCORE, MIN_VOLUME_MULTIPLIER, MIN_VOLATILITY
)
from database import (
    get_all_tracked_pairs, get_pairs_with_users,
    count_signals_today, log_signal, get_all_user_ids
)
from indicators import CANDLES, fetch_price, fetch_candles_binance
from professional_analyzer import ProfessionalAnalyzer

logger = logging.getLogger(__name__)

# Создаём экземпляр анализатора
crypto_micky_analyzer = ProfessionalAnalyzer()

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
    """Сбор рыночных данных для 1h, 4h, 1d таймфреймов"""
    logger.info("🔄 CryptoMicky Price Collector started (1H, 4H, 1D)")
    
    # Загружаем исторические данные для всех таймфреймов
    logger.info("📥 Loading historical data for all timeframes...")
    timeframes = ['1h', '4h', '1d']
    
    for pair in DEFAULT_PAIRS:
        for tf in timeframes:
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
    
    # Регулярное обновление
    async with httpx.AsyncClient() as client:
        while True:
            try:
                pairs = await get_all_tracked_pairs()
                pairs = list(set(pairs + DEFAULT_PAIRS))
                
                ts = time.time()
                for pair in pairs:
                    price_data = await fetch_price(client, pair)
                    if price_data:
                        price, volume = price_data
                        CANDLES.add_candle(pair, "1h", {
                            't': ts, 'o': price, 'h': price,
                            'l': price, 'c': price, 'v': volume
                        })
                
                logger.debug(f"📊 Prices updated for {len(pairs)} pairs")
                await asyncio.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Price collector error: {e}")
                await asyncio.sleep(60)

async def signal_analyzer(bot: Bot):
    """Анализ и отправка сигналов с CryptoMicky алгоритмом"""
    logger.info("🎯 CryptoMicky Signal Analyzer started (60%+ Confidence)")
    
    await asyncio.sleep(10)
    
    while True:
        try:
            rows = await get_pairs_with_users()
            
            pairs_users = defaultdict(list)
            for row in rows:
                pairs_users[row["pair"]].append(row["user_id"])
            
            current_time = time.time()
            signals_found = 0
            
            for pair, users in pairs_users.items():
                # Проверка лимита
                signals_today = await count_signals_today(pair)
                if signals_today >= MAX_SIGNALS_PER_DAY:
                    continue
                
                # Cooldown
                if pair in LAST_SIGNALS:
                    time_since_last = current_time - LAST_SIGNALS[pair]
                    if time_since_last < SIGNAL_COOLDOWN:
                        cooldown_left = int((SIGNAL_COOLDOWN - time_since_last) / 60)
                        logger.debug(f"⏳ {pair}: Cooldown active ({cooldown_left}m left)")
                        continue
                
                # Получаем свечи для всех таймфреймов
                candles_1h = CANDLES.get_candles(pair, "1h")
                candles_4h = CANDLES.get_candles(pair, "4h")
                candles_1d = CANDLES.get_candles(pair, "1d")
                btc_candles_1h = CANDLES.get_candles("BTCUSDT", "1h")
                
                if len(candles_1h) < 100 or len(candles_4h) < 50 or len(candles_1d) < 30:
                    logger.debug(f"⚠️ {pair}: Not enough candles for analysis")
                    continue
                
                signal = crypto_micky_analyzer.analyze_pair(
                    pair, candles_1h, candles_4h, candles_1d, btc_candles_1h
                )
                
                if signal:
                    signals_found += 1
                    logger.info(f"🎯 FOUND SIGNAL: {pair} {signal['side']} ({signal['confidence']}%)")
                    
                    # Определяем Confidence уровень
                    confidence_pct = signal['confidence']
                    if confidence_pct >= 90:
                        confidence_level = "HIGH"
                    elif confidence_pct >= 80:
                        confidence_level = "MEDIUM"
                    else:
                        confidence_level = "LOW"
                    
                    # Формируем сообщение
                    side_emoji = "🟢" if signal['side'] == 'LONG' else "🔴"
                    
                    text = f"{side_emoji} <b>{signal['pair']} — {signal['side']}</b>\n\n"
                    text += "<b>Логика:</b>\n"
                    for reason in signal['reasons']:
                        text += f"• {reason}\n"
                    text += "\n"
                    
                    entry_min, entry_max = signal['entry_zone']
                    text += f"🎯 <b>Вход:</b> {entry_min:.2f} - {entry_max:.2f}\n"
                    text += f"🎯 <b>Цели:</b>\n"
                    text += f"   TP1: {signal['take_profit_1']:.2f}\n"
                    text += f"   TP2: {signal['take_profit_2']:.2f}\n"
                    text += f"   TP3: {signal['take_profit_3']:.2f}\n"
                    text += f"🛡 <b>Стоп:</b> {signal['stop_loss']:.2f}\n\n"
                    text += f"💰 <b>Объём позиции:</b> {signal['position_size']}\n"
                    text += f"📊 <b>Confidence:</b> {confidence_level}\n\n"
                    text += "⚠️ <i>Не финансовый совет</i>"
                    
                    # Отправка
                    sent_count = 0
                    for user_id in users:
                        if await send_message_safe(bot, user_id, text):
                            await log_signal(user_id, pair, signal['side'], signal['price'], signal['confidence'])
                            sent_count += 1
                        await asyncio.sleep(BATCH_SEND_DELAY)
                    
                    LAST_SIGNALS[pair] = current_time
                    logger.info(f"✅ Signal sent: {pair} {signal['side']} to {sent_count} users")
            
            if signals_found > 0:
                logger.info(f"📊 Total signals found: {signals_found}")
            
        except Exception as e:
            logger.error(f"Signal analyzer error: {e}")
        
        await asyncio.sleep(60)
