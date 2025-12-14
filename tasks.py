"""
tasks.py - RARE/HIGH/MEDIUM система сигналов

Пороги:
- 🔥 RARE: ≥95% (без лимита)
- ⚡ HIGH: 80-94% (макс 3/день)
- 📊 MEDIUM: 70-79% (макс 8/день)
- <70% - игнор

Cooldown: 3 часа на пару
Upgrade: Если новый сигнал выше уровнем - отправляем даже в cooldown
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
    SIGNAL_COOLDOWN, COOLDOWN_HOURS_PER_PAIR,
    RARE_CONFIDENCE, HIGH_CONFIDENCE, MIN_CONFIDENCE,
    MAX_RARE_SIGNALS_PER_DAY, MAX_HIGH_SIGNALS_PER_DAY, MAX_MEDIUM_SIGNALS_PER_DAY
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

# Счётчики сигналов по типам
_daily_rare_count = 0
_daily_high_count = 0
_daily_medium_count = 0
_last_reset_date = None

# История последних сигналов по паре (для cooldown + upgrade)
# {pair: {'time': timestamp, 'type': 'MEDIUM'/'HIGH'/'RARE', 'side': 'LONG'/'SHORT', 'confidence': 75.5}}
_pair_last_signal = {}

# Приоритет типов (для upgrade логики)
SIGNAL_PRIORITY = {'MEDIUM': 1, 'HIGH': 2, 'RARE': 3}


def _get_signal_type(confidence: float) -> str:
    """Определить тип сигнала по confidence"""
    if confidence >= RARE_CONFIDENCE:
        return 'RARE'
    elif confidence >= HIGH_CONFIDENCE:
        return 'HIGH'
    elif confidence >= MIN_CONFIDENCE:
        return 'MEDIUM'
    else:
        return None  # Игнор


def _reset_daily_counter():
    """Сброс счётчиков в новый день"""
    global _daily_rare_count, _daily_high_count, _daily_medium_count, _last_reset_date
    today = datetime.now().date()
    if _last_reset_date != today:
        _daily_rare_count = 0
        _daily_high_count = 0
        _daily_medium_count = 0
        _last_reset_date = today
        logger.info(f"📅 New day: reset all signal counters")


def _can_send_signal(signal_type: str) -> bool:
    """Проверка лимита по типу сигнала"""
    _reset_daily_counter()
    if signal_type == 'RARE':
        return _daily_rare_count < MAX_RARE_SIGNALS_PER_DAY
    elif signal_type == 'HIGH':
        return _daily_high_count < MAX_HIGH_SIGNALS_PER_DAY
    elif signal_type == 'MEDIUM':
        return _daily_medium_count < MAX_MEDIUM_SIGNALS_PER_DAY
    return False


def _increment_signal_count(signal_type: str):
    """Увеличить счётчик по типу"""
    global _daily_rare_count, _daily_high_count, _daily_medium_count
    if signal_type == 'RARE':
        _daily_rare_count += 1
        logger.info(f"📊 RARE signals today: {_daily_rare_count}/{MAX_RARE_SIGNALS_PER_DAY}")
    elif signal_type == 'HIGH':
        _daily_high_count += 1
        logger.info(f"📊 HIGH signals today: {_daily_high_count}/{MAX_HIGH_SIGNALS_PER_DAY}")
    elif signal_type == 'MEDIUM':
        _daily_medium_count += 1
        logger.info(f"📊 MEDIUM signals today: {_daily_medium_count}/{MAX_MEDIUM_SIGNALS_PER_DAY}")


def _check_cooldown(pair: str, new_type: str, new_confidence: float) -> tuple:
    """
    Проверка cooldown с логикой upgrade.
    
    Returns:
        (can_send: bool, reason: str)
    """
    if pair not in _pair_last_signal:
        return True, "no_previous"
    
    last = _pair_last_signal[pair]
    time_since = time.time() - last['time']
    cooldown_seconds = COOLDOWN_HOURS_PER_PAIR * 3600
    
    # Cooldown не истёк
    if time_since < cooldown_seconds:
        # Проверяем upgrade: новый тип выше предыдущего?
        old_priority = SIGNAL_PRIORITY.get(last['type'], 0)
        new_priority = SIGNAL_PRIORITY.get(new_type, 0)
        
        if new_priority > old_priority:
            # Upgrade! Разрешаем отправку
            hours_left = (cooldown_seconds - time_since) / 3600
            logger.info(f"⬆️ {pair}: Upgrade {last['type']} → {new_type} (cooldown bypass, {hours_left:.1f}h left)")
            return True, f"upgrade_{last['type']}_to_{new_type}"
        else:
            # Нет upgrade - блокируем
            hours_left = (cooldown_seconds - time_since) / 3600
            return False, f"cooldown_active ({hours_left:.1f}h left)"
    
    return True, "cooldown_expired"


def _record_signal(pair: str, signal_type: str, side: str, confidence: float):
    """Записать отправленный сигнал для cooldown"""
    _pair_last_signal[pair] = {
        'time': time.time(),
        'type': signal_type,
        'side': side,
        'confidence': confidence
    }


def reset_daily_limits():
    """Принудительный сброс всех дневных лимитов (для админ команды)"""
    global _daily_rare_count, _daily_high_count, _daily_medium_count
    _daily_rare_count = 0
    _daily_high_count = 0
    _daily_medium_count = 0
    logger.info("🔄 Daily limits reset by admin")
    return True


def get_daily_limits_info() -> dict:
    """Получить текущие счётчики (для админ команды)"""
    return {
        'rare': {'current': _daily_rare_count, 'max': MAX_RARE_SIGNALS_PER_DAY},
        'high': {'current': _daily_high_count, 'max': MAX_HIGH_SIGNALS_PER_DAY},
        'medium': {'current': _daily_medium_count, 'max': MAX_MEDIUM_SIGNALS_PER_DAY},
        'cooldowns': len(_pair_last_signal)
    }


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
                    confidence_pct = signal['confidence']
                    
                    # 1. Определяем тип сигнала
                    signal_type = _get_signal_type(confidence_pct)
                    
                    # Если confidence < 70% - игнорируем
                    if signal_type is None:
                        logger.debug(f"❌ {pair}: confidence {confidence_pct:.1f}% < 70% - ignored")
                        continue
                    
                    # 2. Проверяем cooldown (с логикой upgrade)
                    can_send, cooldown_reason = _check_cooldown(pair, signal_type, confidence_pct)
                    if not can_send:
                        logger.info(f"⏸️ {pair}: {cooldown_reason}")
                        pairs_skipped += 1
                        continue
                    
                    # 3. Проверяем дневной лимит по типу
                    if not _can_send_signal(signal_type):
                        logger.info(f"⏸️ {pair}: daily_limit_reached for {signal_type}")
                        pairs_skipped += 1
                        continue
                    
                    # 4. Лимит на пару
                    signals_today = await count_signals_today(pair)
                    if signals_today >= MAX_SIGNALS_PER_DAY:
                        logger.info(f"⏸️ {pair}: pair_limit_reached ({signals_today}/{MAX_SIGNALS_PER_DAY})")
                        pairs_skipped += 1
                        continue
                    
                    # ✅ Все проверки пройдены - отправляем!
                    signals_found += 1
                    
                    # Формируем бейдж
                    if signal_type == 'RARE':
                        type_badge = "🔥 RARE"
                    elif signal_type == 'HIGH':
                        type_badge = "⚡ HIGH"
                    else:
                        type_badge = "📊 MEDIUM"
                    
                    logger.info(f"🎯 SIGNAL: {pair} {signal['side']} ({type_badge}, {confidence_pct:.1f}%)")
                    
                    # Формируем сообщение
                    side_emoji = "🟢" if signal['side'] == 'LONG' else "🔴"
                    
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
                    text += f"📊 <b>Confidence:</b> {type_badge}\n\n"
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
                        
                        # Записываем для cooldown
                        _record_signal(pair, signal_type, signal['side'], confidence_pct)
                        
                        # Увеличиваем счётчик по типу
                        _increment_signal_count(signal_type)
                        
                        logger.info(f"✅ Sent {pair} {signal['side']} ({type_badge}) to {sent_count}/{len(users)} users")
            
            # Итог цикла
            logger.info(f"[Cycle {cycle}] Analyzed: {pairs_analyzed}, Skipped: {pairs_skipped}, Signals: {signals_found}")
            
        except Exception as e:
            logger.error(f"Signal analyzer error: {e}", exc_info=True)
        
        # Пауза между циклами
        await asyncio.sleep(60)
