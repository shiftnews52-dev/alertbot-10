"""
tasks_FIXED.py - Исправленная версия с увеличенной загрузкой данных
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
    SIGNAL_COOLDOWN
)
from database import (
    get_all_tracked_pairs, get_pairs_with_users,
    count_signals_today, log_signal, get_all_user_ids
)
from indicators import CANDLES, fetch_price, fetch_candles_binance
from professional_analyzer import CryptoMickyAnalyzer

logger = logging.getLogger(__name__)

crypto_micky_analyzer = CryptoMickyAnalyzer()

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
    """
    Сбор рыночных данных для 1h, 4h, 1d таймфреймов
    
    ИСПРАВЛЕНИЕ: Увеличено количество загружаемых свечей:
    - 1h: 300 свечей (было 100)
    - 4h: 200 свечей (было 100)
    - 1d: 100 свечей (было 100)
    """
    logger.info("🔄 CryptoMicky Price Collector started (1H, 4H, 1D)")
    
    # Загружаем исторические данные
    logger.info("📥 Loading historical data for all timeframes...")
    
    # ИСПРАВЛЕНИЕ: Увеличены лимиты загрузки
    timeframes_config = {
        '1h': 300,  # Было 100, стало 300
        '4h': 200,  # Было 100, стало 200
        '1d': 100   # Было 100, осталось 100
    }
    
    for pair in DEFAULT_PAIRS:
        for tf, limit in timeframes_config.items():
            try:
                logger.info(f"  🔄 Loading {pair} {tf}: {limit} candles...")
                candles = await fetch_candles_binance(pair, tf, limit)
                if candles:
                    for candle in candles:
                        CANDLES.add_candle(pair, tf, candle)
                    logger.info(f"  ✅ Loaded {len(candles)} candles for {pair} {tf}")
                else:
                    logger.warning(f"  ⚠️  Failed to load {pair} {tf}")
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"  ❌ Error loading {pair} {tf}: {e}")
    
    logger.info("✅ Historical data loaded!")
    
    # Выводим статистику
    for pair in DEFAULT_PAIRS:
        candles_1h = len(CANDLES.get_candles(pair, "1h"))
        candles_4h = len(CANDLES.get_candles(pair, "4h"))
        candles_1d = len(CANDLES.get_candles(pair, "1d"))
        
        status = "✅" if (candles_1h >= 100 and candles_4h >= 100 and candles_1d >= 30) else "⚠️"
        logger.info(f"{status} {pair}: 1h={candles_1h}, 4h={candles_4h}, 1d={candles_1d}")
    
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
    """
    Анализ и отправка сигналов с CryptoMicky алгоритмом
    
    ИСПРАВЛЕНИЕ: Добавлены детальные логи для отладки
    """
    logger.info("🎯 CryptoMicky Signal Analyzer started")
    
    # Ждём загрузки данных
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
                    logger.debug(f"⏭️  {pair}: Daily limit reached ({signals_today}/{MAX_SIGNALS_PER_DAY})")
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
                
                # ИСПРАВЛЕНИЕ: Новые требования к данным
                if len(candles_1h) < 100 or len(candles_4h) < 100 or len(candles_1d) < 30:
                    logger.debug(f"⚠️  {pair}: Not enough candles (1h={len(candles_1h)}, 4h={len(candles_4h)}, 1d={len(candles_1d)})")
                    continue
                
                logger.debug(f"🔍 Analyzing {pair} (1h={len(candles_1h)}, 4h={len(candles_4h)}, 1d={len(candles_1d)} candles)...")
                
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
                    elif confidence_pct >= 60:
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
                    text += f"📊 <b>Confidence:</b> {confidence_level} ({confidence_pct}%)\n\n"
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
                else:
                    logger.debug(f"⏭️  {pair}: No signal found")
            
            if signals_found > 0:
                logger.info(f"📊 Total signals found: {signals_found}")
            else:
                logger.debug("⏭️  No signals found in this cycle")
            
        except Exception as e:
            logger.error(f"Signal analyzer error: {e}", exc_info=True)
        
        await asyncio.sleep(60)
