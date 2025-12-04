"""
tasks_STRICT.py - СТРОГАЯ версия с лимитами на сигналы

ИЗМЕНЕНИЯ:
1. Добавлен глобальный лимит GLOBAL_MAX_SIGNALS_PER_DAY
2. Увеличен cooldown между сигналами
3. Проверка на дубликаты
4. Более детальное логирование
"""
import time
import asyncio
import logging
from collections import defaultdict
from datetime import datetime
import httpx
from aiogram import Bot
from aiogram.utils.exceptions import RetryAfter, TelegramAPIError

from config import (
    CHECK_INTERVAL, DEFAULT_PAIRS, TIMEFRAME,
    MAX_SIGNALS_PER_DAY, BATCH_SEND_SIZE, BATCH_SEND_DELAY,
    SIGNAL_COOLDOWN, GLOBAL_MAX_SIGNALS_PER_DAY
)
from database import (
    get_all_tracked_pairs, get_pairs_with_users, get_users_for_pair,
    count_signals_today, log_signal, get_all_paid_users
)
from indicators import CANDLES, fetch_price, fetch_candles_binance
from professional_analyzer import CryptoMickyAnalyzer

logger = logging.getLogger(__name__)

# Анализатор
crypto_micky_analyzer = CryptoMickyAnalyzer()

# Кэш последних сигналов {pair: timestamp}
LAST_SIGNALS = {}

# Счётчик глобальных сигналов за день
_daily_signal_count = 0
_daily_signal_date = None


def _reset_daily_counter():
    """Сбросить счётчик если новый день"""
    global _daily_signal_count, _daily_signal_date
    
    today = datetime.now().date()
    if _daily_signal_date != today:
        _daily_signal_count = 0
        _daily_signal_date = today
        logger.info(f"📅 New day: reset signal counter")


def _can_send_more_signals() -> bool:
    """Проверить можно ли отправлять ещё сигналы"""
    _reset_daily_counter()
    return _daily_signal_count < GLOBAL_MAX_SIGNALS_PER_DAY


def _increment_signal_count():
    """Увеличить счётчик сигналов"""
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
        logger.debug(f"Telegram API error for user {user_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending to {user_id}: {e}")
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
    
    # Выводим статистику
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
                pairs = list(set(await get_all_tracked_pairs() + DEFAULT_PAIRS))
                
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
    """
    Анализ и отправка сигналов со СТРОГИМИ фильтрами
    
    Лимиты:
    - MAX_SIGNALS_PER_DAY = 2 на пару
    - GLOBAL_MAX_SIGNALS_PER_DAY = 10 всего
    - SIGNAL_COOLDOWN = 8 часов
    """
    logger.info("🎯 Signal Analyzer started (STRICT MODE)")
    logger.info(f"   Max signals per pair: {MAX_SIGNALS_PER_DAY}")
    logger.info(f"   Global max signals: {GLOBAL_MAX_SIGNALS_PER_DAY}")
    logger.info(f"   Cooldown: {SIGNAL_COOLDOWN/3600:.0f}h")
    
    # Ждём загрузки данных
    await asyncio.sleep(15)
    
    while True:
        try:
            # Проверяем глобальный лимит
            if not _can_send_more_signals():
                logger.info(f"⏸️ Global limit reached ({GLOBAL_MAX_SIGNALS_PER_DAY} signals today)")
                await asyncio.sleep(300)  # Ждём 5 минут
                continue
            
            # Получаем пары с пользователями
            rows = await get_pairs_with_users()
            
            pairs_users = defaultdict(list)
            for row in rows:
                pairs_users[row["pair"]].append(row["user_id"])
            
            # Добавляем DEFAULT_PAIRS
            for pair in DEFAULT_PAIRS:
                if pair not in pairs_users:
                    pairs_users[pair] = []
            
            current_time = time.time()
            signals_found = 0
            
            for pair, users in pairs_users.items():
                # ============ ПРОВЕРКА 1: Глобальный лимит ============
                if not _can_send_more_signals():
                    logger.info(f"⏸️ Global limit reached, stopping analysis")
                    break
                
                # ============ ПРОВЕРКА 2: Лимит на пару ============
                signals_today = await count_signals_today(pair)
                if signals_today >= MAX_SIGNALS_PER_DAY:
                    logger.debug(f"⏭️ {pair}: Daily limit ({signals_today}/{MAX_SIGNALS_PER_DAY})")
                    continue
                
                # ============ ПРОВЕРКА 3: Cooldown ============
                if pair in LAST_SIGNALS:
                    time_since_last = current_time - LAST_SIGNALS[pair]
                    if time_since_last < SIGNAL_COOLDOWN:
                        hours_left = (SIGNAL_COOLDOWN - time_since_last) / 3600
                        logger.debug(f"⏳ {pair}: Cooldown ({hours_left:.1f}h left)")
                        continue
                
                # ============ ПРОВЕРКА 4: Достаточно данных ============
                candles_1h = CANDLES.get_candles(pair, "1h")
                candles_4h = CANDLES.get_candles(pair, "4h")
                candles_1d = CANDLES.get_candles(pair, "1d")
                btc_candles = CANDLES.get_candles("BTCUSDT", "1h")
                
                if len(candles_1h) < 100 or len(candles_4h) < 100 or len(candles_1d) < 30:
                    continue
                
                # ============ АНАЛИЗ ============
                signal = crypto_micky_analyzer.analyze_pair(
                    pair, candles_1h, candles_4h, candles_1d, btc_candles
                )
                
                if signal:
                    signals_found += 1
                    confidence = signal['confidence']
                    
                    logger.info(f"🎯 SIGNAL: {pair} {signal['side']} ({confidence}%)")
                    
                    # Уровень confidence
                    if confidence >= 90:
                        confidence_level = "🔥 HIGH"
                    elif confidence >= 80:
                        confidence_level = "✅ MEDIUM"
                    else:
                        confidence_level = "⚡ STANDARD"
                    
                    # Формируем сообщение
                    side_emoji = "🟢" if signal['side'] == 'LONG' else "🔴"
                    
                    text = f"{side_emoji} <b>{signal['pair']} — {signal['side']}</b>\n"
                    text += f"📊 Confidence: {confidence_level} ({confidence}%)\n\n"
                    
                    text += "<b>📋 Анализ:</b>\n"
                    for reason in signal['reasons']:
                        text += f"  {reason}\n"
                    text += "\n"
                    
                    entry_min, entry_max = signal['entry_zone']
                    text += f"💰 <b>Вход:</b> {entry_min:.2f} - {entry_max:.2f}\n\n"
                    
                    text += f"🎯 <b>Цели:</b>\n"
                    text += f"   TP1: {signal['take_profit_1']:.2f} (R:R 2:1)\n"
                    text += f"   TP2: {signal['take_profit_2']:.2f} (R:R 4:1)\n"
                    text += f"   TP3: {signal['take_profit_3']:.2f} (R:R 6:1)\n\n"
                    
                    text += f"🛡 <b>Стоп:</b> {signal['stop_loss']:.2f}\n"
                    text += f"💼 <b>Объём:</b> {signal['position_size']}\n\n"
                    
                    text += "⚠️ <i>Не финансовый совет. Торгуй ответственно.</i>"
                    
                    # Получаем пользователей
                    if not users:
                        users = await get_users_for_pair(pair)
                    if not users:
                        users = await get_all_paid_users()
                    
                    # Отправляем
                    sent_count = 0
                    for user_id in users:
                        if await send_message_safe(bot, user_id, text, parse_mode="HTML"):
                            sent_count += 1
                        await asyncio.sleep(BATCH_SEND_DELAY)
                    
                    # Логируем
                    await log_signal(pair, signal['side'], signal['price'], confidence)
                    
                    # Обновляем кэш и счётчики
                    LAST_SIGNALS[pair] = current_time
                    _increment_signal_count()
                    
                    logger.info(f"✅ Sent to {sent_count} users | Total today: {_daily_signal_count}/{GLOBAL_MAX_SIGNALS_PER_DAY}")
            
            if signals_found > 0:
                logger.info(f"📊 Cycle complete: {signals_found} signals found")
            
        except Exception as e:
            logger.error(f"Signal analyzer error: {e}", exc_info=True)
        
        # Пауза между циклами анализа
        await asyncio.sleep(60)
