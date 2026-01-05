"""
tasks.py - PRO/FREE система сигналов

PRO доступ (только качественные сигналы):
- 🔥 RARE: ≥95% — макс 1/день, сразу
- ⚡ HIGH: 80-94% — макс 2/день, сразу
- ❌ MEDIUM: НЕ получают (только FREE)
- Сообщение "рынок шумный" если 0 RARE/HIGH за день

FREE доступ (постоянный):
- 📊 MEDIUM: 70-79% — макс 1/день
- Задержка 45 минут после генерации
- Скрыты: TP2, TP3, Stop Loss
- Байт-сообщение после сигнала

Signal Tracking:
- Автоматические updates (вход, TP1, TP2, TP3, SL)
"""
import time
import asyncio
import logging
import random
from datetime import datetime, timezone
from collections import defaultdict
from typing import Optional, Dict, List
import httpx
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import RetryAfter, TelegramAPIError

from config import (
    CHECK_INTERVAL, DEFAULT_PAIRS, TIMEFRAME,
    MAX_SIGNALS_PER_DAY, BATCH_SEND_SIZE, BATCH_SEND_DELAY,
    SIGNAL_COOLDOWN, COOLDOWN_HOURS_PER_PAIR,
    RARE_CONFIDENCE, HIGH_CONFIDENCE, MIN_CONFIDENCE,
    MAX_RARE_SIGNALS_PER_DAY, MAX_HIGH_SIGNALS_PER_DAY, MAX_MEDIUM_SIGNALS_PER_DAY,
    HIGH_TIME_SLOTS, MIN_INTERVAL_RARE, MIN_INTERVAL_HIGH, MIN_INTERVAL_MEDIUM,
    SIGNAL_QUEUE_TTL, SIGNAL_PRICE_TOLERANCE,
    FREE_SIGNAL_DELAY, FREE_MAX_SIGNALS_PER_DAY,
    TRACKING_ENABLED, NO_SIGNALS_MESSAGE_ENABLED, NO_SIGNALS_HOUR_UTC
)
from database import (
    get_all_tracked_pairs, get_pairs_with_users,
    count_signals_today, log_signal, get_all_user_ids, get_user_lang,
    get_pro_users, get_free_users, get_users_by_lang,
    add_active_signal, get_active_signals, update_signal_status, close_signal,
    add_signal_to_history, mark_signal_sent_to_free, get_pending_free_signals,
    is_duplicate_signal, get_daily_counts, increment_daily_count, can_send_signal,
    get_signals_sent_today
)
from indicators import CANDLES, fetch_price, fetch_candles_binance
from professional_analyzer import CryptoMickyAnalyzer

logger = logging.getLogger(__name__)

crypto_micky_analyzer = CryptoMickyAnalyzer()


# ==================== БАЙТ-СООБЩЕНИЯ ДЛЯ FREE ====================
UPSELL_MESSAGES_RU = [
    """💎 <b>PRO пользователи получили этот сигнал 45 минут назад</b>
и уже видят TP2, TP3 и Stop Loss

→ Не упускай лучшие входы""",

    """🔥 <b>Этот сигнал в PRO был отправлен раньше</b>
+ полные цели + защитный стоп

Пока ты ждёшь — другие уже в позиции""",

    """⚡ <b>FREE = 1 сигнал/день с задержкой</b>
PRO = все сигналы сразу + RARE + HIGH

Разница ощущается на балансе 💰""",

    """🎯 <b>В PRO версии ты бы уже знал:</b>
• Куда ставить стоп
• Где фиксировать прибыль
• Весь план сделки""",

    """⏰ <b>45 минут — это много на рынке</b>

PRO получают сигналы мгновенно
+ RARE сигналы (лучшие сетапы)
+ Полную информацию""",

    """📊 <b>FREE показывает стиль</b>
PRO даёт контроль

Один пропущенный RARE = потерянная прибыль""",
]

UPSELL_MESSAGES_EN = [
    """💎 <b>PRO users got this signal 45 minutes ago</b>
and already see TP2, TP3 and Stop Loss

→ Don't miss the best entries""",

    """🔥 <b>This signal was sent to PRO earlier</b>
+ full targets + protective stop

While you wait — others are already in position""",

    """⚡ <b>FREE = 1 signal/day with delay</b>
PRO = all signals instantly + RARE + HIGH

The difference shows in your balance 💰""",

    """🎯 <b>In PRO you would already know:</b>
• Where to set stop
• Where to take profit
• The complete trade plan""",

    """⏰ <b>45 minutes is a lot in the market</b>

PRO gets signals instantly
+ RARE signals (best setups)
+ Full information""",

    """📊 <b>FREE shows the style</b>
PRO gives control

One missed RARE = lost profit""",
]


def get_upsell_message(lang: str = "ru") -> str:
    """Получить случайное байт-сообщение"""
    messages = UPSELL_MESSAGES_RU if lang == "ru" else UPSELL_MESSAGES_EN
    return random.choice(messages)


# ==================== ФОРМАТИРОВАНИЕ СИГНАЛОВ ====================

def format_signal_pro(signal: dict, signal_type: str, lang: str = "ru") -> str:
    """
    Форматирование ПОЛНОГО сигнала для PRO
    """
    # Бейдж типа
    if signal_type == 'RARE':
        type_badge = "🔥 RARE"
    elif signal_type == 'HIGH':
        type_badge = "⚡ HIGH"
    else:
        type_badge = "📊 MEDIUM"
    
    side_emoji = "🟢" if signal['side'] == 'LONG' else "🔴"
    entry_min, entry_max = signal['entry_zone']
    
    if lang == "en":
        text = f"{type_badge}\n\n"
        text += f"{side_emoji} <b>{signal['pair']} — {signal['side']}</b>\n\n"
        text += f"🎯 <b>Entry:</b> {entry_min:.4f} - {entry_max:.4f}\n\n"
        text += f"✅ TP1: {signal['take_profit_1']:.4f}\n"
        text += f"✅ TP2: {signal['take_profit_2']:.4f}\n"
        text += f"✅ TP3: {signal['take_profit_3']:.4f}\n\n"
        text += f"🛡 <b>Stop:</b> {signal['stop_loss']:.4f}\n\n"
        text += "⚠️ <i>Not financial advice</i>"
    else:
        text = f"{type_badge}\n\n"
        text += f"{side_emoji} <b>{signal['pair']} — {signal['side']}</b>\n\n"
        text += f"🎯 <b>Вход:</b> {entry_min:.4f} - {entry_max:.4f}\n\n"
        text += f"✅ TP1: {signal['take_profit_1']:.4f}\n"
        text += f"✅ TP2: {signal['take_profit_2']:.4f}\n"
        text += f"✅ TP3: {signal['take_profit_3']:.4f}\n\n"
        text += f"🛡 <b>Стоп:</b> {signal['stop_loss']:.4f}\n\n"
        text += "⚠️ <i>Не финансовый совет</i>"
    
    return text


def format_signal_free(signal: dict, lang: str = "ru") -> str:
    """
    Форматирование УРЕЗАННОГО сигнала для FREE
    - Только TP1
    - Скрыты TP2, TP3, Stop Loss
    - Пометка о задержке
    """
    side_emoji = "🟢" if signal['side'] == 'LONG' else "🔴"
    entry_min, entry_max = signal['entry_zone']
    
    if lang == "en":
        text = f"📊 FREE SIGNAL\n"
        text += f"<i>⏰ Delayed 45 min</i>\n\n"
        text += f"{side_emoji} <b>{signal['pair']} — {signal['side']}</b>\n\n"
        text += f"🎯 <b>Entry:</b> {entry_min:.4f} - {entry_max:.4f}\n\n"
        text += f"✅ TP1: {signal['take_profit_1']:.4f}\n"
        text += f"🔒 TP2: <i>PRO only</i>\n"
        text += f"🔒 TP3: <i>PRO only</i>\n\n"
        text += f"🔒 <b>Stop:</b> <i>PRO only</i>\n\n"
        text += "⚠️ <i>Not financial advice</i>"
    else:
        text = f"📊 FREE СИГНАЛ\n"
        text += f"<i>⏰ Задержка 45 мин</i>\n\n"
        text += f"{side_emoji} <b>{signal['pair']} — {signal['side']}</b>\n\n"
        text += f"🎯 <b>Вход:</b> {entry_min:.4f} - {entry_max:.4f}\n\n"
        text += f"✅ TP1: {signal['take_profit_1']:.4f}\n"
        text += f"🔒 TP2: <i>Только PRO</i>\n"
        text += f"🔒 TP3: <i>Только PRO</i>\n\n"
        text += f"🔒 <b>Стоп:</b> <i>Только PRO</i>\n\n"
        text += "⚠️ <i>Не финансовый совет</i>"
    
    return text


# Алиас для совместимости
def format_signal(signal: dict, signal_type: str, lang: str = "ru") -> str:
    return format_signal_pro(signal, signal_type, lang)


LAST_SIGNALS = {}

# Счётчики сигналов по типам
_daily_rare_count = 0
_daily_high_count = 0
_daily_medium_count = 0
_last_reset_date = None

# Счётчики по временным окнам для HIGH (индекс окна -> использовано)
_high_slots_used = {}  # {slot_index: True/False}

# Время последнего сигнала по типу (для интервалов)
_last_signal_time = {'RARE': 0, 'HIGH': 0, 'MEDIUM': 0}

# История последних сигналов по паре (для cooldown + upgrade)
_pair_last_signal = {}

# Очередь отложенных сигналов
# [{signal_data, queued_at, users, pair}]
_signal_queue: List[Dict] = []

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
    global _daily_rare_count, _daily_high_count, _daily_medium_count, _last_reset_date, _high_slots_used
    today = datetime.now(timezone.utc).date()
    if _last_reset_date != today:
        _daily_rare_count = 0
        _daily_high_count = 0
        _daily_medium_count = 0
        _high_slots_used = {}  # Сброс использованных окон
        _last_reset_date = today
        logger.info(f"📅 New day: reset all signal counters and time slots")


def _get_current_high_slot() -> Optional[int]:
    """Получить индекс текущего временного окна для HIGH (или None если вне окон)"""
    now = datetime.now(timezone.utc)
    current_hour = now.hour
    
    for idx, (start, end) in enumerate(HIGH_TIME_SLOTS):
        if start <= current_hour < end:
            return idx
    return None


def _is_high_slot_available() -> tuple:
    """Проверить доступно ли текущее окно для HIGH сигнала"""
    slot = _get_current_high_slot()
    
    if slot is None:
        return False, "outside_time_window"
    
    if _high_slots_used.get(slot, False):
        return False, f"slot_{slot}_already_used"
    
    return True, f"slot_{slot}_available"


def _check_type_interval(signal_type: str) -> tuple:
    """Проверить прошёл ли минимальный интервал с последнего сигнала этого типа"""
    last_time = _last_signal_time.get(signal_type, 0)
    now = time.time()
    
    if signal_type == 'RARE':
        min_interval = MIN_INTERVAL_RARE * 60
    elif signal_type == 'HIGH':
        min_interval = MIN_INTERVAL_HIGH * 60
    else:
        min_interval = MIN_INTERVAL_MEDIUM * 60
    
    time_since = now - last_time
    
    if time_since < min_interval:
        minutes_left = (min_interval - time_since) / 60
        return False, f"interval_wait ({minutes_left:.0f}min left)"
    
    return True, "interval_ok"


def _can_send_signal(signal_type: str) -> tuple:
    """
    Проверка возможности отправки сигнала PRO (лимит + временное окно + интервал)
    
    ВАЖНО: Лимиты RARE/HIGH применяются к PRO
    Лимит MEDIUM НЕ применяется к PRO - они получают все MEDIUM
    Лимит MEDIUM применяется только к FREE через can_send_signal(is_free=True)
    """
    _reset_daily_counter()
    
    # 1. Проверка дневного лимита (только RARE и HIGH для PRO)
    if signal_type == 'RARE':
        if _daily_rare_count >= MAX_RARE_SIGNALS_PER_DAY:
            return False, "daily_limit_reached"
    elif signal_type == 'HIGH':
        if _daily_high_count >= MAX_HIGH_SIGNALS_PER_DAY:
            return False, "daily_limit_reached"
        # Проверка временного окна для HIGH
        slot_ok, slot_reason = _is_high_slot_available()
        if not slot_ok:
            return False, slot_reason
    # MEDIUM - БЕЗ лимита для PRO (лимит только для FREE)
    
    # 2. Проверка минимального интервала
    interval_ok, interval_reason = _check_type_interval(signal_type)
    if not interval_ok:
        return False, interval_reason
    
    return True, "can_send"


def _increment_signal_count(signal_type: str):
    """Увеличить счётчик по типу и записать время"""
    global _daily_rare_count, _daily_high_count, _daily_medium_count
    
    # Записываем время последнего сигнала
    _last_signal_time[signal_type] = time.time()
    
    if signal_type == 'RARE':
        _daily_rare_count += 1
        logger.info(f"📊 RARE signals today: {_daily_rare_count}/{MAX_RARE_SIGNALS_PER_DAY}")
    elif signal_type == 'HIGH':
        _daily_high_count += 1
        # Помечаем окно как использованное
        slot = _get_current_high_slot()
        if slot is not None:
            _high_slots_used[slot] = True
        logger.info(f"📊 HIGH signals today: {_daily_high_count}/{MAX_HIGH_SIGNALS_PER_DAY} (slot {slot} used)")
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


def _add_to_queue(signal_data: Dict, users: List[int], pair: str, signal_type: str):
    """Добавить сигнал в очередь ожидания"""
    _signal_queue.append({
        'signal': signal_data,
        'users': users,
        'pair': pair,
        'type': signal_type,
        'queued_at': time.time(),
        'entry_price': signal_data['price']
    })
    logger.info(f"📥 {pair} {signal_type} added to queue (queue size: {len(_signal_queue)})")


def _check_signal_still_valid(queued_signal: Dict, current_price: float) -> tuple:
    """Проверить актуален ли сигнал из очереди"""
    # 1. Проверка TTL
    age_minutes = (time.time() - queued_signal['queued_at']) / 60
    if age_minutes > SIGNAL_QUEUE_TTL:
        return False, f"expired (age: {age_minutes:.0f}min)"
    
    # 2. Проверка цены
    entry_price = queued_signal['entry_price']
    price_diff_pct = abs(current_price - entry_price) / entry_price * 100
    
    if price_diff_pct > SIGNAL_PRICE_TOLERANCE:
        return False, f"price_moved ({price_diff_pct:.1f}%)"
    
    return True, "valid"


async def process_signal_queue(bot: Bot):
    """Обработка очереди отложенных сигналов"""
    global _signal_queue
    
    if not _signal_queue:
        return
    
    # Сортируем по приоритету (RARE > HIGH > MEDIUM)
    _signal_queue.sort(key=lambda x: SIGNAL_PRIORITY.get(x['type'], 0), reverse=True)
    
    new_queue = []
    
    for queued in _signal_queue:
        signal_type = queued['type']
        pair = queued['pair']
        
        # Проверяем можем ли отправить сейчас
        can_send, reason = _can_send_signal(signal_type)
        
        if can_send:
            # Получаем текущую цену для проверки актуальности
            try:
                from indicators import fetch_price
                async with httpx.AsyncClient() as client:
                    price_data = await fetch_price(client, pair)
                    current_price = price_data[0] if price_data else queued['entry_price']
            except:
                current_price = queued['entry_price']
            
            # Проверяем актуальность
            is_valid, valid_reason = _check_signal_still_valid(queued, current_price)
            
            if is_valid:
                # Отправляем!
                signal = queued['signal']
                users = queued['users']
                
                signal_type_badge = "🔥 RARE" if signal_type == 'RARE' else "⚡ HIGH" if signal_type == 'HIGH' else "📊 MEDIUM"
                
                logger.info(f"📤 Sending queued signal: {pair} {signal_type_badge}")
                
                # Группируем юзеров по языку
                from database import get_users_by_lang
                users_by_lang = await get_users_by_lang(users)
                
                # Отправка по языкам
                sent_count = 0
                
                for lang, lang_users in users_by_lang.items():
                    if not lang_users:
                        continue
                    
                    text = format_signal(signal, signal_type, lang)
                    
                    for user_id in lang_users:
                        success = await send_message_safe(bot, user_id, text, parse_mode="HTML")
                        if success:
                            sent_count += 1
                        await asyncio.sleep(BATCH_SEND_DELAY)
                
                if sent_count > 0:
                    from database import log_signal
                    await log_signal(pair, signal['side'], signal['price'], signal['confidence'])
                    LAST_SIGNALS[pair] = time.time()
                    _record_signal(pair, signal_type, signal['side'], signal['confidence'])
                    _increment_signal_count(signal_type)
                    logger.info(f"✅ Sent queued {pair} ({signal_type_badge}) to {sent_count}/{len(users)} users")
            else:
                logger.info(f"🗑️ Removed from queue: {pair} - {valid_reason}")
        else:
            # Не можем отправить сейчас - оставляем в очереди
            # Но проверяем не протух ли
            age_minutes = (time.time() - queued['queued_at']) / 60
            if age_minutes <= SIGNAL_QUEUE_TTL:
                new_queue.append(queued)
            else:
                logger.info(f"🗑️ Expired in queue: {pair} (age: {age_minutes:.0f}min)")
    
    _signal_queue = new_queue


def reset_daily_limits():
    """Принудительный сброс всех дневных лимитов (для админ команды)"""
    global _daily_rare_count, _daily_high_count, _daily_medium_count, _high_slots_used
    _daily_rare_count = 0
    _daily_high_count = 0
    _daily_medium_count = 0
    _high_slots_used = {}
    logger.info("🔄 Daily limits reset by admin")
    return True


def get_daily_limits_info() -> dict:
    """Получить текущие счётчики (для админ команды)"""
    current_slot = _get_current_high_slot()
    slots_info = []
    for idx, (start, end) in enumerate(HIGH_TIME_SLOTS):
        used = "✅" if _high_slots_used.get(idx, False) else "⏳" if idx == current_slot else "⬜"
        slots_info.append(f"{used} {start}:00-{end}:00")
    
    return {
        'rare': {'current': _daily_rare_count, 'max': MAX_RARE_SIGNALS_PER_DAY},
        'high': {'current': _daily_high_count, 'max': MAX_HIGH_SIGNALS_PER_DAY},
        'medium': {'current': _daily_medium_count, 'max': MAX_MEDIUM_SIGNALS_PER_DAY},
        'high_slots': slots_info,
        'current_slot': current_slot,
        'cooldowns': len(_pair_last_signal),
        'queue_size': len(_signal_queue)
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
                    can_send_cd, cooldown_reason = _check_cooldown(pair, signal_type, confidence_pct)
                    if not can_send_cd:
                        logger.info(f"⏸️ {pair}: {cooldown_reason}")
                        pairs_skipped += 1
                        continue
                    
                    # 3. Лимит на пару
                    signals_today = await count_signals_today(pair)
                    if signals_today >= MAX_SIGNALS_PER_DAY:
                        logger.info(f"⏸️ {pair}: pair_limit_reached ({signals_today}/{MAX_SIGNALS_PER_DAY})")
                        pairs_skipped += 1
                        continue
                    
                    # 4. Проверяем возможность отправки (лимит + окно + интервал)
                    can_send, send_reason = _can_send_signal(signal_type)
                    
                    if not can_send:
                        # Не можем отправить сейчас - добавляем в очередь
                        logger.info(f"📥 {pair}: {send_reason} - adding to queue")
                        _add_to_queue(signal, users, pair, signal_type)
                        continue
                    
                    # ✅ Проверка на дублирование в БД
                    if await is_duplicate_signal(pair, signal['side'], signal['price']):
                        logger.info(f"⏭️ {pair}: Duplicate signal in DB, skipping")
                        pairs_skipped += 1
                        continue
                    
                    # ✅ Проверка лимитов из БД
                    can_send_db, db_reason = await can_send_signal(signal_type)
                    if not can_send_db:
                        logger.info(f"⏸️ {pair}: {db_reason}")
                        continue
                    
                    # ✅ Все проверки пройдены
                    signals_found += 1
                    
                    # Формируем бейдж
                    if signal_type == 'RARE':
                        type_badge = "🔥 RARE"
                    elif signal_type == 'HIGH':
                        type_badge = "⚡ HIGH"
                    else:
                        type_badge = "📊 MEDIUM"
                    
                    logger.info(f"🎯 SIGNAL: {pair} {signal['side']} ({type_badge}, {confidence_pct:.1f}%)")
                    
                    # Сохраняем в историю
                    history_id = await add_signal_to_history(
                        pair, signal['side'], signal_type, 
                        signal['price'], confidence_pct
                    )
                    
                    # Добавляем в active_signals для tracking
                    entry_min, entry_max = signal['entry_zone']
                    await add_active_signal(
                        pair, signal['side'], signal_type, signal['price'],
                        entry_min, entry_max,
                        signal['take_profit_1'], signal['take_profit_2'], signal['take_profit_3'],
                        signal['stop_loss']
                    )
                    
                    # ===== PRO НЕ ПОЛУЧАЮТ MEDIUM =====
                    # MEDIUM сигналы только для FREE (с задержкой)
                    if signal_type == 'MEDIUM':
                        logger.info(f"📊 {pair} MEDIUM saved for FREE only (PRO skip)")
                        # Логируем и обновляем счётчики
                        await log_signal(pair, signal['side'], signal['price'], signal['confidence'])
                        LAST_SIGNALS[pair] = current_time
                        _record_signal(pair, signal_type, signal['side'], confidence_pct)
                        _increment_signal_count(signal_type)
                        await increment_daily_count(signal_type)
                        continue  # Не отправляем PRO, идём к следующей паре
                    
                    # ===== RARE и HIGH → отправляем PRO =====
                    # Получаем PRO юзеров и группируем по языку
                    pro_users = await get_pro_users()
                    # Фильтруем только тех кто в users (подписан на эту пару)
                    pro_users_filtered = [u for u in pro_users if u in users]
                    
                    if pro_users_filtered:
                        users_by_lang = await get_users_by_lang(pro_users_filtered)
                        
                        # Отправка PRO по языкам
                        sent_count = 0
                        
                        for lang, lang_users in users_by_lang.items():
                            if not lang_users:
                                continue
                            
                            text = format_signal_pro(signal, signal_type, lang)
                            
                            for user_id in lang_users:
                                success = await send_message_safe(bot, user_id, text, parse_mode="HTML")
                                if success:
                                    sent_count += 1
                                await asyncio.sleep(BATCH_SEND_DELAY)
                        
                        logger.info(f"✅ Sent {pair} {signal['side']} ({type_badge}) to {sent_count} PRO users")
                    else:
                        logger.info(f"ℹ️ No PRO users for {pair}")
                    
                    # Логируем и обновляем счётчики
                    await log_signal(pair, signal['side'], signal['price'], signal['confidence'])
                    LAST_SIGNALS[pair] = current_time
                    
                    # Записываем для cooldown
                    _record_signal(pair, signal_type, signal['side'], confidence_pct)
                    
                    # Увеличиваем счётчик по типу
                    _increment_signal_count(signal_type)
                    
                    # Увеличиваем счётчик в БД
                    await increment_daily_count(signal_type)
            
            # Обработка очереди отложенных сигналов
            await process_signal_queue(bot)
            
            # Отправка FREE сигналов (с задержкой 45 мин)
            await send_delayed_free_signals(bot)
            
            # Итог цикла
            queue_size = len(_signal_queue)
            logger.info(f"[Cycle {cycle}] Analyzed: {pairs_analyzed}, Skipped: {pairs_skipped}, Signals: {signals_found}, Queue: {queue_size}")
            
        except Exception as e:
            logger.error(f"Signal analyzer error: {e}", exc_info=True)
        
        # Пауза между циклами
        await asyncio.sleep(60)


async def send_delayed_free_signals(bot: Bot):
    """
    Отправка FREE сигналов с задержкой 45 минут
    Только MEDIUM сигналы, макс 1 в день
    FREE получают ВСЕ MEDIUM сигналы (не по подпискам на пары)
    """
    try:
        # Проверяем лимит FREE
        can_send_free, reason = await can_send_signal('MEDIUM', is_free=True)
        
        # Получаем сигналы готовые к отправке FREE
        pending_signals = await get_pending_free_signals()
        
        # Логируем статус
        logger.info(f"📭 FREE check: can_send={can_send_free}, pending={len(pending_signals) if pending_signals else 0}, reason={reason}")
        
        if not can_send_free:
            return
        
        if not pending_signals:
            return
        
        # Берём первый (самый старый)
        signal_data = pending_signals[0]
        
        logger.info(f"📤 Sending FREE signal: {signal_data['pair']} {signal_data['side']} (delayed 45min)")
        
        # Получаем FREE юзеров
        free_users = await get_free_users()
        
        if not free_users:
            logger.info("ℹ️ No FREE users to send signal")
            # Отмечаем как отправленный чтобы не застрял
            await mark_signal_sent_to_free(signal_data['id'])
            return
        
        logger.info(f"📊 Found {len(free_users)} FREE users")
        
        # Получаем полные данные сигнала из active_signals
        from database import get_active_signal_by_pair
        full_signal = await get_active_signal_by_pair(signal_data['pair'], signal_data['side'])
        
        if full_signal:
            signal = {
                'pair': signal_data['pair'],
                'side': signal_data['side'],
                'price': signal_data['entry_price'],
                'entry_zone': (full_signal['entry_min'], full_signal['entry_max']),
                'take_profit_1': full_signal['tp1'],
                'take_profit_2': full_signal['tp2'],
                'take_profit_3': full_signal['tp3'],
                'stop_loss': full_signal['stop_loss'],
            }
        else:
            # Fallback - рассчитываем примерно
            price = signal_data['entry_price']
            is_long = signal_data['side'] == 'LONG'
            signal = {
                'pair': signal_data['pair'],
                'side': signal_data['side'],
                'price': price,
                'entry_zone': (price * 0.99, price * 1.01),
                'take_profit_1': price * (1.02 if is_long else 0.98),
                'take_profit_2': price * (1.04 if is_long else 0.96),
                'take_profit_3': price * (1.06 if is_long else 0.94),
                'stop_loss': price * (0.98 if is_long else 1.02),
            }
        
        # Группируем по языку
        users_by_lang = await get_users_by_lang(free_users)
        
        sent_count = 0
        
        for lang, lang_users in users_by_lang.items():
            if not lang_users:
                continue
            
            # Урезанный сигнал
            text = format_signal_free(signal, lang)
            
            for user_id in lang_users:
                success = await send_message_safe(bot, user_id, text, parse_mode="HTML")
                if success:
                    sent_count += 1
                    
                    # Отправляем байт-сообщение через 3 сек
                    await asyncio.sleep(3)
                    
                    upsell_text = get_upsell_message(lang)
                    kb = InlineKeyboardMarkup()
                    btn_text = "💎 Upgrade to PRO" if lang == "en" else "💎 Перейти на PRO"
                    kb.add(InlineKeyboardButton(btn_text, callback_data="show_pricing"))
                    
                    await send_message_safe(bot, user_id, upsell_text, reply_markup=kb, parse_mode="HTML")
                
                await asyncio.sleep(BATCH_SEND_DELAY)
        
        # Отмечаем как отправленный FREE
        await mark_signal_sent_to_free(signal_data['id'])
        
        # Увеличиваем счётчик FREE
        await increment_daily_count('MEDIUM', is_free=True)
        
        logger.info(f"✅ FREE signal sent to {sent_count}/{len(free_users)} users")
        
        logger.info(f"✅ FREE signal sent to {sent_count} users")
        
    except Exception as e:
        logger.error(f"Error sending FREE signals: {e}", exc_info=True)


async def signal_tracker(bot: Bot):
    """
    Фоновая задача для отслеживания активных сигналов
    Отправляет updates когда цена достигает entry/TP/SL
    """
    from config import TRACKING_ENABLED, ENTRY_ACTIVATION_TOLERANCE
    
    if not TRACKING_ENABLED:
        logger.info("📊 Signal Tracker disabled")
        return
    
    logger.info("📊 Signal Tracker started")
    
    await asyncio.sleep(120)  # Ждём загрузки данных
    
    async with httpx.AsyncClient() as client:
        while True:
            try:
                active_signals = await get_active_signals()
                
                for sig in active_signals:
                    pair = sig['pair']
                    
                    # Получаем текущую цену
                    price_data = await fetch_price(client, pair)
                    if not price_data:
                        continue
                    
                    current_price = price_data[0]
                    is_long = sig['side'] == 'LONG'
                    
                    # Проверяем вход
                    if not sig['entry_hit']:
                        entry_min = sig['entry_min'] or sig['entry_price'] * 0.995
                        entry_max = sig['entry_max'] or sig['entry_price'] * 1.005
                        
                        if entry_min <= current_price <= entry_max:
                            await update_signal_status(sig['id'], 'entry_hit', 1)
                            await send_update_message(bot, pair, sig['side'], 'ENTRY', current_price)
                            logger.info(f"🎯 {pair} Entry activated at {current_price}")
                    
                    # Проверяем TP1
                    if sig['entry_hit'] and not sig['tp1_hit']:
                        if (is_long and current_price >= sig['tp1']) or \
                           (not is_long and current_price <= sig['tp1']):
                            await update_signal_status(sig['id'], 'tp1_hit', 1)
                            await send_update_message(bot, pair, sig['side'], 'TP1', current_price)
                            logger.info(f"✅ {pair} TP1 hit at {current_price}")
                    
                    # Проверяем TP2
                    if sig['tp1_hit'] and not sig['tp2_hit']:
                        if (is_long and current_price >= sig['tp2']) or \
                           (not is_long and current_price <= sig['tp2']):
                            await update_signal_status(sig['id'], 'tp2_hit', 1)
                            await send_update_message(bot, pair, sig['side'], 'TP2', current_price)
                            logger.info(f"✅ {pair} TP2 hit at {current_price}")
                    
                    # Проверяем TP3 (закрытие в прибыль)
                    if sig['tp2_hit'] and not sig['tp3_hit']:
                        if (is_long and current_price >= sig['tp3']) or \
                           (not is_long and current_price <= sig['tp3']):
                            await update_signal_status(sig['id'], 'tp3_hit', 1)
                            profit = ((sig['tp3'] / sig['entry_price']) - 1) * 100 if is_long else \
                                     (1 - (sig['tp3'] / sig['entry_price'])) * 100
                            await close_signal(sig['id'], profit)
                            await send_update_message(bot, pair, sig['side'], 'TP3', current_price, profit)
                            logger.info(f"🎉 {pair} TP3 hit! Profit: {profit:.1f}%")
                    
                    # Проверяем SL (закрытие в минус)
                    if sig['entry_hit'] and not sig['sl_hit'] and not sig['tp3_hit']:
                        if (is_long and current_price <= sig['stop_loss']) or \
                           (not is_long and current_price >= sig['stop_loss']):
                            await update_signal_status(sig['id'], 'sl_hit', 1)
                            loss = ((sig['stop_loss'] / sig['entry_price']) - 1) * 100 if is_long else \
                                   (1 - (sig['stop_loss'] / sig['entry_price'])) * 100
                            await close_signal(sig['id'], loss)
                            await send_update_message(bot, pair, sig['side'], 'SL', current_price, loss)
                            logger.info(f"❌ {pair} SL hit! Loss: {loss:.1f}%")
                    
                    await asyncio.sleep(0.1)
                
                await asyncio.sleep(60)  # Проверка раз в минуту
                
            except Exception as e:
                logger.error(f"Signal tracker error: {e}", exc_info=True)
                await asyncio.sleep(60)


async def send_update_message(bot: Bot, pair: str, side: str, update_type: str, 
                              price: float, profit_percent: float = None):
    """Отправить update сообщение всем PRO юзерам"""
    try:
        pro_users = await get_pro_users()
        
        if not pro_users:
            return
        
        users_by_lang = await get_users_by_lang(pro_users)
        
        side_emoji = "🟢" if side == 'LONG' else "🔴"
        
        for lang, lang_users in users_by_lang.items():
            if not lang_users:
                continue
            
            if lang == "en":
                if update_type == 'ENTRY':
                    text = f"🎯 <b>ENTRY ACTIVATED</b>\n\n{side_emoji} {pair} {side}\n📍 Price: {price:.4f}"
                elif update_type == 'TP1':
                    text = f"✅ <b>TP1 HIT!</b>\n\n{side_emoji} {pair} {side}\n📍 Price: {price:.4f}\n\n💡 Move stop to entry"
                elif update_type == 'TP2':
                    text = f"✅ <b>TP2 HIT!</b>\n\n{side_emoji} {pair} {side}\n📍 Price: {price:.4f}\n\n💡 Take partial profit"
                elif update_type == 'TP3':
                    text = f"🎉 <b>TP3 HIT - FULL TARGET!</b>\n\n{side_emoji} {pair} {side}\n📍 Price: {price:.4f}\n\n💰 Profit: +{profit_percent:.1f}%"
                elif update_type == 'SL':
                    text = f"❌ <b>STOP LOSS HIT</b>\n\n{side_emoji} {pair} {side}\n📍 Price: {price:.4f}\n\n📉 Loss: {profit_percent:.1f}%"
            else:
                if update_type == 'ENTRY':
                    text = f"🎯 <b>ВХОД АКТИВИРОВАН</b>\n\n{side_emoji} {pair} {side}\n📍 Цена: {price:.4f}"
                elif update_type == 'TP1':
                    text = f"✅ <b>TP1 ДОСТИГНУТ!</b>\n\n{side_emoji} {pair} {side}\n📍 Цена: {price:.4f}\n\n💡 Перенеси стоп в безубыток"
                elif update_type == 'TP2':
                    text = f"✅ <b>TP2 ДОСТИГНУТ!</b>\n\n{side_emoji} {pair} {side}\n📍 Цена: {price:.4f}\n\n💡 Зафиксируй часть прибыли"
                elif update_type == 'TP3':
                    text = f"🎉 <b>TP3 ДОСТИГНУТ - ПОЛНАЯ ЦЕЛЬ!</b>\n\n{side_emoji} {pair} {side}\n📍 Цена: {price:.4f}\n\n💰 Прибыль: +{profit_percent:.1f}%"
                elif update_type == 'SL':
                    text = f"❌ <b>СТОП-ЛОСС СРАБОТАЛ</b>\n\n{side_emoji} {pair} {side}\n📍 Цена: {price:.4f}\n\n📉 Убыток: {profit_percent:.1f}%"
            
            for user_id in lang_users:
                await send_message_safe(bot, user_id, text, parse_mode="HTML")
                await asyncio.sleep(BATCH_SEND_DELAY)
                
    except Exception as e:
        logger.error(f"Error sending update: {e}")


async def no_signals_notifier(bot: Bot):
    """
    Отправляет PRO юзерам сообщение 'рынок шумный' если за день не было RARE/HIGH сигналов
    FREE юзеры не получают это сообщение (они получают MEDIUM)
    """
    if not NO_SIGNALS_MESSAGE_ENABLED:
        return
    
    logger.info("📭 No Signals Notifier started (PRO only, RARE+HIGH check)")
    
    await asyncio.sleep(300)  # Ждём 5 мин после старта
    
    last_notification_date = None
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            today = now.strftime('%Y-%m-%d')
            
            # Отправляем в указанный час если ещё не отправляли сегодня
            if now.hour == NO_SIGNALS_HOUR_UTC and last_notification_date != today:
                # Проверяем только RARE и HIGH (PRO сигналы)
                rare_today = _daily_rare_count
                high_today = _daily_high_count
                pro_signals_today = rare_today + high_today
                
                logger.info(f"📭 PRO signals today: RARE={rare_today}, HIGH={high_today}, total={pro_signals_today}")
                
                if pro_signals_today == 0:
                    logger.info("📭 Sending 'noisy market' message to PRO users")
                    
                    # Получаем только PRO юзеров
                    pro_users = await get_pro_users()
                    
                    if not pro_users:
                        logger.info("📭 No PRO users to notify")
                        last_notification_date = today
                        continue
                    
                    users_by_lang = await get_users_by_lang(pro_users)
                    
                    for lang, lang_users in users_by_lang.items():
                        if not lang_users:
                            continue
                        
                        if lang == "en":
                            text = """🌊 <b>Noisy Market Today</b>

The market is too volatile and unpredictable today.

We didn't find any setups that meet our strict criteria for RARE or HIGH signals.

This happens sometimes — it's better to stay out than to trade in chaos.

🎯 <b>No trade is better than a bad trade.</b>

See you tomorrow with fresh opportunities!"""
                        else:
                            text = """🌊 <b>Сегодня рынок шумный</b>

Рынок сегодня слишком волатильный и непредсказуемый.

Мы не нашли сетапов, которые соответствуют нашим строгим критериям для RARE или HIGH сигналов.

Такое бывает — лучше остаться вне рынка, чем торговать в хаосе.

🎯 <b>Лучше без сделки, чем плохая сделка.</b>

До завтра, с новыми возможностями!"""
                        
                        for user_id in lang_users:
                            await send_message_safe(bot, user_id, text, parse_mode="HTML")
                            await asyncio.sleep(BATCH_SEND_DELAY)
                    
                    last_notification_date = today
                    logger.info(f"📭 'Noisy market' sent to {len(pro_users)} PRO users")
                else:
                    last_notification_date = today  # Помечаем день как обработанный
            
            await asyncio.sleep(3600)  # Проверка раз в час
            
        except Exception as e:
            logger.error(f"No signals notifier error: {e}", exc_info=True)
            await asyncio.sleep(3600)


async def subscription_manager(bot: Bot):
    """
    Фоновая задача для управления подписками:
    - Очистка истёкших подписок
    - Напоминания за 2 дня
    - Уведомления об истечении
    - Промо для неподписанных
    """
    from config import (
        REMINDER_DAYS_BEFORE, PROMO_INTERVAL_HOURS, 
        NOTIFICATION_HOUR_UTC
    )
    from database import (
        get_users_expiring_soon, mark_reminder_sent,
        get_expired_subscriptions, expire_subscription,
        get_users_for_promo, update_promo_sent,
        get_all_expired_to_cleanup, get_user_lang
    )
    from promo_messages import (
        get_reminder_2_days, get_expired_message, 
        get_promo_hook, get_promo_count
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    logger.info("📧 Subscription Manager started")
    
    # Ждём инициализации
    await asyncio.sleep(60)
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            current_hour = now.hour
            
            # ==================== 1. ОЧИСТКА ИСТЁКШИХ ====================
            expired_ids = await get_all_expired_to_cleanup()
            if expired_ids:
                logger.info(f"🧹 Cleaning up {len(expired_ids)} expired subscriptions")
                for user_id in expired_ids:
                    await expire_subscription(user_id)
            
            # Остальные действия только в определённое время (не спамим ночью)
            if current_hour == NOTIFICATION_HOUR_UTC:
                
                # ==================== 2. НАПОМИНАНИЯ ЗА 2 ДНЯ ====================
                expiring_users = await get_users_expiring_soon(REMINDER_DAYS_BEFORE)
                if expiring_users:
                    logger.info(f"⏰ Sending {len(expiring_users)} expiry reminders")
                    
                    for user in expiring_users:
                        try:
                            text = get_reminder_2_days(user["lang"])
                            
                            # Кнопка продления со скидкой
                            kb = InlineKeyboardMarkup()
                            btn_text = "🎁 Продлить -25%" if user["lang"] == "ru" else "🎁 Renew -25%"
                            kb.add(InlineKeyboardButton(btn_text, callback_data="renew_discount"))
                            
                            await bot.send_message(user["user_id"], text, reply_markup=kb, parse_mode="HTML")
                            await mark_reminder_sent(user["user_id"])
                            await asyncio.sleep(0.1)
                            
                            logger.info(f"📧 Reminder sent to {user['user_id']}")
                        except Exception as e:
                            logger.warning(f"Failed to send reminder to {user['user_id']}: {e}")
                
                # ==================== 3. УВЕДОМЛЕНИЯ ОБ ИСТЕЧЕНИИ ====================
                expired_users = await get_expired_subscriptions()
                if expired_users:
                    logger.info(f"❌ Sending {len(expired_users)} expiry notifications")
                    
                    for user in expired_users:
                        try:
                            text = get_expired_message(user["lang"])
                            
                            kb = InlineKeyboardMarkup()
                            btn_text = "🎁 Продлить -25%" if user["lang"] == "ru" else "🎁 Renew -25%"
                            kb.add(InlineKeyboardButton(btn_text, callback_data="renew_discount"))
                            
                            await bot.send_message(user["user_id"], text, reply_markup=kb, parse_mode="HTML")
                            await expire_subscription(user["user_id"])
                            await asyncio.sleep(0.1)
                            
                            logger.info(f"📧 Expiry notification sent to {user['user_id']}")
                        except Exception as e:
                            logger.warning(f"Failed to send expiry notification to {user['user_id']}: {e}")
                
                # ==================== 4. ПРОМО ДЛЯ НЕПОДПИСАННЫХ ====================
                promo_users = await get_users_for_promo(PROMO_INTERVAL_HOURS)
                promo_count = get_promo_count()
                
                if promo_users:
                    logger.info(f"💰 Sending promo to {len(promo_users)} users")
                    
                    for user in promo_users:
                        try:
                            # Следующий индекс (циклически)
                            next_index = (user["last_index"] + 1) % promo_count
                            text, _ = get_promo_hook(user["lang"], next_index)
                            
                            kb = InlineKeyboardMarkup()
                            btn_text = "🚀 Подписаться" if user["lang"] == "ru" else "🚀 Subscribe"
                            kb.add(InlineKeyboardButton(btn_text, callback_data="show_pricing"))
                            
                            await bot.send_message(user["user_id"], text, reply_markup=kb, parse_mode="HTML")
                            await update_promo_sent(user["user_id"], next_index)
                            await asyncio.sleep(0.1)
                            
                            logger.info(f"📧 Promo #{next_index} sent to {user['user_id']}")
                        except Exception as e:
                            logger.warning(f"Failed to send promo to {user['user_id']}: {e}")
            
            # Проверяем раз в час
            await asyncio.sleep(3600)
            
        except Exception as e:
            logger.error(f"Subscription manager error: {e}", exc_info=True)
            await asyncio.sleep(300)
