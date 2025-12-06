"""
tasks.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
- Логирование на уровне INFO (видно в Render)
- Глобальный лимит сигналов
"""
import time
import asyncio
import logging
from datetime import datetime
from collections import defaultdict
import httpx
from aiogram import Bot
from aiogram.utils.exceptions import RetryAfter, TelegramAPIError

from config import (
    CHECK_INTERVAL, DEFAULT_PAIRS, TIMEFRAME,
    MAX_SIGNALS_PER_DAY, BATCH_SEND_SIZE, BATCH_SEND_DELAY,
    SIGNAL_COOLDOWN, GLOBAL_MAX_SIGNALS_PER_DAY
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

# Глобальный счётчик сигналов
_daily_signal_count = 0
_last_reset_date = None


def _reset_daily_counter():
    """Сброс счётчика в новый день"""
    global _daily_signal_count, _last_reset_date
    today = datetime.now().date()
    if _last_reset_date != today:
        _daily_signal_count = 0
        _last_reset_date = today
        logger.info(f"📅 New day: reset signal counter")


def _can_send_more_signals() -> bool:
    """Проверка глобального лимита"""
    _reset_daily_counter()
    return _daily_signal_count < GLOBAL_MAX_SIGNALS_PER_DAY


def _increment_signal_count():
    """Увеличить счётчик"""
    global _daily_signal_count
    _daily_signal_count += 1
    logger.info(f"📊 Signals today: {_daily_signal_count}/{GLOBAL_MAX_SIGNALS_PER_DAY}")


async def send_message_safe(bot: Bot, user_id: int, text: str, **kwargs):
    """Безопасная отправка с обработкой rate limit"""
    try:
        await bot.send_message(user_id, text, **kwargs)
        return True
    except RetryAfter as e:
        await asyncio.sleep(e.timeout)
        return await send_message_safe(bot, user_id, text, **kwargs)
    except TelegramAPIError as e:
        logger.warning(f"Failed to send to {user_id}: {e}")
        return False


async def price_collector(bot: Bot):
    """Сбор рыночных данных для 1h, 4h, 1d таймфреймов"""
    logger.info("🔄 Price Collector started (1H, 4H, 1D)")
    
    # Загружаем исторические данные
    logger.info("📥 Loading historical data...")
    
    timeframes_config = {
        '1h': 300,
        '4h': 200,
        '1d': 100
    }
    
    for pair in DEFAULT_PAIRS:
        for tf, limit in timeframes_config.items():
            try:
                candles = await fetch_candles_binance(pair, tf, limit)
                if candles:
                    for candle in candles:
                        CANDLES.add_candle(pair, tf, candle)
                    logger.info(f"  ✅ {pair} {tf}: {len(candles)} candles")
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"  ❌ {pair} {tf}: {e}")
    
    logger.info("✅ Historical data loaded!")
    
    # Статистика
    for pair in DEFAULT_PAIRS:
        c1h = len(CANDLES.get_candles(pair, "1h"))
        c4h = len(CANDLES.get_candles(pair, "4h"))
        c1d = len(CANDLES.get_candles(pair, "1d"))
        status = "✅" if (c1h >= 100 and c4h >= 100 and c1d >= 30) else "⚠️"
        logger.info(f"{status} {pair}: 1h={c1h}, 4h={c4h}, 1d={c1d}")
    
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
                
                await asyncio.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Price collector error: {e}")
                await asyncio.sleep(60)


async def signal_analyzer(bot: Bot):
    """Анализ и отправка сигналов"""
    logger.info("🎯 Signal Analyzer started")
    
    # Ждём загрузки данных
    await asyncio.sleep(30)
    logger.info("🔍 Starting analysis loop...")
    
    cycle = 0
    
    while True:
        try:
            cycle += 1
            _reset_daily_counter()
            
            # Проверка глобального лимита
            if not _can_send_more_signals():
                logger.info(f"⏸️ Daily limit reached ({_daily_signal_count}/{GLOBAL_MAX_SIGNALS_PER_DAY})")
                await asyncio.sleep(300)
                continue
            
            rows = await get_pairs_with_users()
            
            if not rows:
                logger.info(f"[Cycle {cycle}] No users with active pairs")
                await asyncio.sleep(60)
                continue
            
            pairs_users = defaultdict(list)
            for row in rows:
                pairs_users[row["pair"]].append(row["user_id"])
            
            logger.info(f"[Cycle {cycle}] Analyzing {len(pairs_users)} pairs...")
            
            current_time = time.time()
            signals_found = 0
            pairs_analyzed = 0
            pairs_skipped = 0
            
            for pair, users in pairs_users.items():
                # Глобальный лимит
                if not _can_send_more_signals():
                    logger.info(f"⏸️ Global limit reached, stopping")
                    break
                
                # Лимит на пару
                signals_today = await count_signals_today(pair)
                if signals_today >= MAX_SIGNALS_PER_DAY:
                    pairs_skipped += 1
                    continue
                
                # Cooldown
                if pair in LAST_SIGNALS:
                    time_since_last = current_time - LAST_SIGNALS[pair]
                    if time_since_last < SIGNAL_COOLDOWN:
                        pairs_skipped += 1
                        continue
                
                # Получаем свечи
                candles_1h = CANDLES.get_candles(pair, "1h")
                candles_4h = CANDLES.get_candles(pair, "4h")
                candles_1d = CANDLES.get_candles(pair, "1d")
                btc_candles_1h = CANDLES.get_candles("BTCUSDT", "1h")
                
                # Проверка данных
                if len(candles_1h) < 100 or len(candles_4h) < 50 or len(candles_1d) < 30:
                    logger.warning(f"⚠️ {pair}: Not enough data (1h={len(candles_1h)}, 4h={len(candles_4h)}, 1d={len(candles_1d)})")
                    continue
                
                pairs_analyzed += 1
                
                # АНАЛИЗ
                signal = crypto_micky_analyzer.analyze_pair(
                    pair, candles_1h, candles_4h, candles_1d, btc_candles_1h
                )
                
                if signal:
                    signals_found += 1
                    logger.info(f"🎯 SIGNAL: {pair} {signal['side']} (confidence: {signal['confidence']}%)")
                    
                    # Формируем сообщение
                    side_emoji = "🟢" if signal['side'] == 'LONG' else "🔴"
                    
                    confidence_pct = signal['confidence']
                    if confidence_pct >= 85:
                        confidence_level = "🔥 HIGH"
                    elif confidence_pct >= 70:
                        confidence_level = "✅ MEDIUM"
                    else:
                        confidence_level = "⚡ LOW"
                    
                    text = f"{side_emoji} <b>{signal['pair']} — {signal['side']}</b>\n\n"
                    text += "<b>Логика:</b>\n"
                    for reason in signal['reasons'][:5]:  # Макс 5 причин
                        text += f"• {reason}\n"
                    text += "\n"
                    
                    entry_min, entry_max = signal['entry_zone']
                    text += f"🎯 <b>Вход:</b> {entry_min:.4f} - {entry_max:.4f}\n"
                    text += f"🎯 <b>Цели:</b>\n"
                    text += f"   TP1: {signal['take_profit_1']:.4f}\n"
                    text += f"   TP2: {signal['take_profit_2']:.4f}\n"
                    text += f"   TP3: {signal['take_profit_3']:.4f}\n"
                    text += f"🛡 <b>Стоп:</b> {signal['stop_loss']:.4f}\n\n"
                    text += f"📊 <b>Confidence:</b> {confidence_level}\n\n"
                    text += "⚠️ <i>Не финансовый совет</i>"
                    
                    # Отправка
                    sent_count = 0
                    for user_id in users:
                        success = await send_message_safe(bot, user_id, text, parse_mode="HTML")
                        if success:
                            sent_count += 1
                        await asyncio.sleep(BATCH_SEND_DELAY)
                    
                    if sent_count > 0:
                        await log_signal(pair, signal['side'], signal['price'], signal['confidence'])
                        LAST_SIGNALS[pair] = current_time
                        _increment_signal_count()
                        logger.info(f"✅ Sent {pair} {signal['side']} to {sent_count}/{len(users)} users")
            
            # Итог цикла
            logger.info(f"[Cycle {cycle}] Analyzed: {pairs_analyzed}, Skipped: {pairs_skipped}, Signals: {signals_found}")
            
        except Exception as e:
            logger.error(f"Signal analyzer error: {e}", exc_info=True)
        
        # Пауза между циклами
        await asyncio.sleep(60)
