"""
indicators.py - Профессиональная логика анализа (ИСПРАВЛЕНО)
ИСПРАВЛЕНИЯ:
1. Добавлен таймфрейм 1d в tf_map
2. Добавлены недостающие функции для test_indicators.py
3. Улучшен расчёт ATR и TP/SL
4. FALLBACK: Binance → Bybit → OKX при блокировке
"""
import time
import logging
from typing import Optional, Dict, List, Tuple
from collections import defaultdict
import httpx

from config import *

logger = logging.getLogger(__name__)

# Текущий активный источник данных
ACTIVE_SOURCE = "binance"  # binance, bybit, okx

class CandleStorage:
    def __init__(self):
        self.candles: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
    
    def add_candle(self, pair: str, tf: str, candle: dict):
        self.candles[pair][tf].append(candle)
        if len(self.candles[pair][tf]) > 500:
            self.candles[pair][tf] = self.candles[pair][tf][-500:]
    
    def get_candles(self, pair: str, tf: str) -> List[dict]:
        return self.candles[pair].get(tf, [])

CANDLES = CandleStorage()

class PriceCache:
    def __init__(self, ttl: int = 30):
        self.cache = {}
        self.ttl = ttl
    
    def get(self, pair: str):
        if pair in self.cache:
            price, volume, cached_at = self.cache[pair]
            if time.time() - cached_at < self.ttl:
                return price, volume
        return None
    
    def set(self, pair: str, price: float, volume: float):
        self.cache[pair] = (price, volume, time.time())
    
    def clear_old(self):
        now = time.time()
        self.cache = {k: v for k, v in self.cache.items() if now - v[2] < self.ttl}

PRICE_CACHE = PriceCache()

# ==================== КОНВЕРТАЦИЯ СИМВОЛОВ ====================
def to_okx_symbol(pair: str) -> str:
    """BTCUSDT -> BTC-USDT"""
    pair = pair.upper()
    if pair.endswith("USDT"):
        return pair[:-4] + "-USDT"
    return pair

def from_okx_symbol(symbol: str) -> str:
    """BTC-USDT -> BTCUSDT"""
    return symbol.replace("-", "")

# ==================== BINANCE API ====================
async def fetch_price_binance(client: httpx.AsyncClient, pair: str) -> Optional[Tuple[float, float]]:
    """Получить цену с Binance"""
    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair.upper()}"
        resp = await client.get(url, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        price = float(data["lastPrice"])
        volume = float(data["volume"])
        return price, volume
    except Exception as e:
        if "418" in str(e):
            logger.warning(f"Binance blocked (418), switching to fallback")
        raise

async def fetch_candles_binance_internal(client: httpx.AsyncClient, pair: str, tf: str, limit: int = 100) -> List[dict]:
    """Получение свечей с Binance"""
    tf_map = {"1h": "1h", "4h": "4h", "1d": "1d"}
    interval = tf_map.get(tf, "1h")
    
    url = f"https://api.binance.com/api/v3/klines"
    params = {"symbol": pair, "interval": interval, "limit": limit}
    
    response = await client.get(url, params=params, timeout=10.0)
    response.raise_for_status()
    
    klines = response.json()
    candles = []
    
    for kline in klines:
        candle = {
            't': kline[0] / 1000,
            'o': float(kline[1]),
            'h': float(kline[2]),
            'l': float(kline[3]),
            'c': float(kline[4]),
            'v': float(kline[5])
        }
        candles.append(candle)
    
    return candles

# ==================== BYBIT API ====================
async def fetch_price_bybit(client: httpx.AsyncClient, pair: str) -> Optional[Tuple[float, float]]:
    """Получить цену с Bybit"""
    try:
        url = f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={pair.upper()}"
        resp = await client.get(url, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("retCode") == 0 and data.get("result", {}).get("list"):
            ticker = data["result"]["list"][0]
            price = float(ticker["lastPrice"])
            volume = float(ticker.get("volume24h", 0))
            return price, volume
        return None
    except Exception as e:
        logger.error(f"Bybit error {pair}: {e}")
        raise

async def fetch_candles_bybit(client: httpx.AsyncClient, pair: str, tf: str, limit: int = 100) -> List[dict]:
    """Получение свечей с Bybit"""
    # Bybit intervals: 1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, M, W
    tf_map = {"1h": "60", "4h": "240", "1d": "D"}
    interval = tf_map.get(tf, "60")
    
    url = f"https://api.bybit.com/v5/market/kline"
    params = {"category": "spot", "symbol": pair.upper(), "interval": interval, "limit": limit}
    
    response = await client.get(url, params=params, timeout=10.0)
    response.raise_for_status()
    
    data = response.json()
    if data.get("retCode") != 0:
        raise Exception(f"Bybit API error: {data.get('retMsg')}")
    
    klines = data.get("result", {}).get("list", [])
    candles = []
    
    # Bybit возвращает в обратном порядке (новые первые)
    for kline in reversed(klines):
        candle = {
            't': int(kline[0]) / 1000,
            'o': float(kline[1]),
            'h': float(kline[2]),
            'l': float(kline[3]),
            'c': float(kline[4]),
            'v': float(kline[5])
        }
        candles.append(candle)
    
    return candles

# ==================== OKX API ====================
async def fetch_price_okx(client: httpx.AsyncClient, pair: str) -> Optional[Tuple[float, float]]:
    """Получить цену с OKX"""
    try:
        okx_symbol = to_okx_symbol(pair)
        url = f"https://www.okx.com/api/v5/market/ticker?instId={okx_symbol}"
        resp = await client.get(url, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("code") == "0" and data.get("data"):
            ticker = data["data"][0]
            price = float(ticker["last"])
            volume = float(ticker.get("vol24h", 0))
            return price, volume
        return None
    except Exception as e:
        logger.error(f"OKX error {pair}: {e}")
        raise

async def fetch_candles_okx(client: httpx.AsyncClient, pair: str, tf: str, limit: int = 100) -> List[dict]:
    """Получение свечей с OKX"""
    # OKX intervals: 1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 6H, 12H, 1D, 1W, 1M
    tf_map = {"1h": "1H", "4h": "4H", "1d": "1D"}
    interval = tf_map.get(tf, "1H")
    
    okx_symbol = to_okx_symbol(pair)
    url = f"https://www.okx.com/api/v5/market/candles"
    params = {"instId": okx_symbol, "bar": interval, "limit": str(limit)}
    
    response = await client.get(url, params=params, timeout=10.0)
    response.raise_for_status()
    
    data = response.json()
    if data.get("code") != "0":
        raise Exception(f"OKX API error: {data.get('msg')}")
    
    klines = data.get("data", [])
    candles = []
    
    # OKX возвращает в обратном порядке (новые первые)
    for kline in reversed(klines):
        candle = {
            't': int(kline[0]) / 1000,
            'o': float(kline[1]),
            'h': float(kline[2]),
            'l': float(kline[3]),
            'c': float(kline[4]),
            'v': float(kline[5])
        }
        candles.append(candle)
    
    return candles

# ==================== УНИВЕРСАЛЬНЫЕ ФУНКЦИИ С FALLBACK ====================
async def fetch_price(client: httpx.AsyncClient, pair: str) -> Optional[Tuple[float, float]]:
    """Получить цену с автоматическим fallback"""
    global ACTIVE_SOURCE
    
    # Проверяем кэш
    cached = PRICE_CACHE.get(pair)
    if cached:
        return cached
    
    sources = [
        ("binance", fetch_price_binance),
        ("bybit", fetch_price_bybit),
        ("okx", fetch_price_okx),
    ]
    
    # Начинаем с активного источника
    if ACTIVE_SOURCE != "binance":
        sources = sorted(sources, key=lambda x: 0 if x[0] == ACTIVE_SOURCE else 1)
    
    for source_name, fetch_func in sources:
        try:
            result = await fetch_func(client, pair)
            if result:
                price, volume = result
                PRICE_CACHE.set(pair, price, volume)
                
                if source_name != ACTIVE_SOURCE:
                    logger.info(f"✅ Switched to {source_name.upper()} for price data")
                    ACTIVE_SOURCE = source_name
                
                return price, volume
        except Exception as e:
            if "418" in str(e) or "teapot" in str(e).lower():
                logger.warning(f"⚠️ {source_name.upper()} blocked, trying next...")
            continue
    
    logger.error(f"❌ All sources failed for {pair}")
    return None

async def fetch_candles_binance(pair: str, tf: str, limit: int = 100):
    """Получение свечей с автоматическим fallback"""
    global ACTIVE_SOURCE
    
    sources = [
        ("binance", fetch_candles_binance_internal),
        ("bybit", fetch_candles_bybit),
        ("okx", fetch_candles_okx),
    ]
    
    # Начинаем с активного источника
    if ACTIVE_SOURCE != "binance":
        sources = sorted(sources, key=lambda x: 0 if x[0] == ACTIVE_SOURCE else 1)
    
    async with httpx.AsyncClient() as client:
        for source_name, fetch_func in sources:
            try:
                candles = await fetch_func(client, pair, tf, limit)
                if candles:
                    if source_name != ACTIVE_SOURCE:
                        logger.info(f"✅ Switched to {source_name.upper()} for candle data")
                        ACTIVE_SOURCE = source_name
                    
                    return candles
            except Exception as e:
                if "418" in str(e) or "teapot" in str(e).lower():
                    logger.warning(f"⚠️ {source_name.upper()} blocked for {pair} {tf}, trying next...")
                else:
                    logger.error(f"Error {source_name} {pair} {tf}: {e}")
                continue
    
    logger.error(f"❌ All sources failed for {pair} {tf}")
    return None

# ==================== ИНДИКАТОРЫ ====================
def calculate_rsi(closes: List[float], period: int = RSI_PERIOD) -> Optional[float]:
    """Расчёт RSI"""
    if len(closes) < period + 1:
        return None
    
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        gains.append(max(0, change))
        losses.append(max(0, -change))
    
    if len(gains) < period:
        return None
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# Алиас для совместимости с test_indicators.py
def rsi(closes: List[float], period: int = RSI_PERIOD) -> Optional[float]:
    """Алиас для calculate_rsi"""
    return calculate_rsi(closes, period)


def calculate_ema(values: List[float], period: int) -> Optional[float]:
    """Exponential Moving Average"""
    if len(values) < period:
        return None
    
    k = 2 / (period + 1)
    ema_val = values[0]
    for value in values[1:]:
        ema_val = value * k + ema_val * (1 - k)
    return ema_val


# Алиас для совместимости с test_indicators.py
def ema(values: List[float], period: int) -> Optional[float]:
    """Алиас для calculate_ema"""
    return calculate_ema(values, period)


def sma(values: List[float], period: int) -> Optional[float]:
    """Simple Moving Average"""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def calculate_macd(closes: List[float]) -> Optional[Tuple[float, float, float]]:
    """MACD с сигнальной линией и гистограммой"""
    if len(closes) < MACD_SLOW + MACD_SIGNAL:
        return None
    
    ema_fast = calculate_ema(closes, MACD_FAST)
    ema_slow = calculate_ema(closes, MACD_SLOW)
    
    if ema_fast is None or ema_slow is None:
        return None
    
    macd_line = ema_fast - ema_slow
    
    # Рассчитываем MACD для всех точек чтобы получить сигнальную линию
    macd_values = []
    for i in range(MACD_SLOW, len(closes) + 1):
        ema_f = calculate_ema(closes[:i], MACD_FAST)
        ema_s = calculate_ema(closes[:i], MACD_SLOW)
        if ema_f and ema_s:
            macd_values.append(ema_f - ema_s)
    
    if len(macd_values) < MACD_SIGNAL:
        signal_line = macd_line
    else:
        signal_line = calculate_ema(macd_values, MACD_SIGNAL)
        if signal_line is None:
            signal_line = macd_line
    
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram


# Алиас для совместимости с test_indicators.py
def macd(closes: List[float]) -> Optional[Tuple[float, float, float]]:
    """Алиас для calculate_macd"""
    return calculate_macd(closes)


def bollinger_bands(closes: List[float], period: int = BB_PERIOD, std_dev: float = BB_STD) -> Optional[Tuple[float, float, float]]:
    """Bollinger Bands"""
    if len(closes) < period:
        return None
    
    recent = closes[-period:]
    middle = sum(recent) / period
    
    # Стандартное отклонение
    variance = sum((x - middle) ** 2 for x in recent) / period
    std = variance ** 0.5
    
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    
    return upper, middle, lower


def volume_strength(candles: List[dict], period: int = 20) -> Optional[float]:
    """Сила объёма относительно среднего"""
    if len(candles) < period:
        return None
    
    volumes = [c.get('v', 0) for c in candles[-period:]]
    avg_volume = sum(volumes[:-1]) / (period - 1) if period > 1 else volumes[0]
    
    if avg_volume == 0:
        return None
    
    current_volume = volumes[-1]
    return current_volume / avg_volume


def atr(candles: List[dict], period: int = 14) -> Optional[float]:
    """Average True Range"""
    if len(candles) < period + 1:
        return None
    
    true_ranges = []
    for i in range(1, len(candles)):
        high = candles[i].get('h', 0)
        low = candles[i].get('l', 0)
        prev_close = candles[i-1].get('c', 0)
        
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        true_ranges.append(tr)
    
    if len(true_ranges) < period:
        return None
    
    return sum(true_ranges[-period:]) / period


def calculate_tp_sl(entry: float, side: str, atr_value: float) -> Dict:
    """
    Расчёт Take Profit и Stop Loss на основе ATR
    
    Risk/Reward:
    - TP1: 2:1 (2x ATR от входа)
    - TP2: 4:1 (4x ATR от входа)
    - TP3: 6:1 (6x ATR от входа)
    - SL: 1x ATR
    """
    if side.upper() == 'LONG':
        stop_loss = entry - atr_value
        tp1 = entry + (atr_value * 2)
        tp2 = entry + (atr_value * 4)
        tp3 = entry + (atr_value * 6)
    else:  # SHORT
        stop_loss = entry + atr_value
        tp1 = entry - (atr_value * 2)
        tp2 = entry - (atr_value * 4)
        tp3 = entry - (atr_value * 6)
    
    # Расчёт процентов
    sl_percent = abs((stop_loss - entry) / entry * 100)
    tp1_percent = abs((tp1 - entry) / entry * 100)
    tp2_percent = abs((tp2 - entry) / entry * 100)
    tp3_percent = abs((tp3 - entry) / entry * 100)
    
    return {
        'stop_loss': stop_loss,
        'take_profit_1': tp1,
        'take_profit_2': tp2,
        'take_profit_3': tp3,
        'sl_percent': sl_percent,
        'tp1_percent': tp1_percent,
        'tp2_percent': tp2_percent,
        'tp3_percent': tp3_percent,
        'risk_reward_1': round(tp1_percent / sl_percent, 1) if sl_percent > 0 else 0,
        'risk_reward_2': round(tp2_percent / sl_percent, 1) if sl_percent > 0 else 0,
        'risk_reward_3': round(tp3_percent / sl_percent, 1) if sl_percent > 0 else 0,
    }


# ==================== АНАЛИЗ ТРЕНДА ====================
def determine_trend(closes: List[float]) -> str:
    """Определение тренда по цене и RSI"""
    if len(closes) < 30:
        return 'neutral'
    
    # Анализ структуры цены
    recent = closes[-20:]
    highs = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i-1])
    lows = sum(1 for i in range(1, len(recent)) if recent[i] < recent[i-1])
    
    # RSI анализ
    rsi_val = calculate_rsi(closes)
    if rsi_val is None:
        return 'neutral'
    
    # EMA анализ
    ema_short = calculate_ema(closes, 9)
    ema_long = calculate_ema(closes, 21)
    
    bull_conditions = 0
    bear_conditions = 0
    
    # Бычьи условия
    if highs > lows:
        bull_conditions += 1
    if rsi_val > 50:
        bull_conditions += 1
    if ema_short and ema_long and ema_short > ema_long:
        bull_conditions += 1
    
    # Медвежьи условия
    if lows > highs:
        bear_conditions += 1
    if rsi_val < 50:
        bear_conditions += 1
    if ema_short and ema_long and ema_short < ema_long:
        bear_conditions += 1
    
    if bull_conditions >= 2:
        return 'bullish'
    elif bear_conditions >= 2:
        return 'bearish'
    else:
        return 'neutral'

# ==================== ПОИСК УРОВНЕЙ ====================
def find_support_resistance_levels(candles: List[dict], window: int = 5) -> Tuple[List[float], List[float]]:
    """Поиск качественных уровней поддержки/сопротивления"""
    if len(candles) < window * 3:
        return [], []
    
    highs = [c['h'] for c in candles]
    lows = [c['l'] for c in candles]
    closes = [c['c'] for c in candles]
    
    resistance_levels = []
    support_levels = []
    
    # Ищем локальные экстремумы
    for i in range(window, len(candles) - window):
        current_high = highs[i]
        current_low = lows[i]
        
        # Проверяем максимум
        is_local_max = True
        for j in range(1, window + 1):
            if current_high < highs[i - j] or current_high < highs[i + j]:
                is_local_max = False
                break
        
        # Проверяем минимум
        is_local_min = True
        for j in range(1, window + 1):
            if current_low > lows[i - j] or current_low > lows[i + j]:
                is_local_min = False
                break
        
        if is_local_max:
            resistance_levels.append(current_high)
        if is_local_min:
            support_levels.append(current_low)
    
    # Фильтруем и группируем уровни
    resistance_levels = _filter_and_group_levels(resistance_levels, closes)
    support_levels = _filter_and_group_levels(support_levels, closes)
    
    return support_levels, resistance_levels

def _filter_and_group_levels(levels: List[float], closes: List[float]) -> List[float]:
    """Фильтрация и группировка уровней"""
    if not levels:
        return []
    
    current_price = closes[-1] if closes else 0
    
    # Убираем уровни слишком далеко от текущей цены
    filtered_levels = []
    for level in levels:
        price_diff_pct = abs(level - current_price) / current_price
        if price_diff_pct <= 0.1:  # Не дальше 10%
            filtered_levels.append(level)
    
    if not filtered_levels:
        return []
    
    # Группируем близкие уровни
    filtered_levels.sort()
    grouped = []
    current_group = [filtered_levels[0]]
    
    for level in filtered_levels[1:]:
        if abs(level - current_group[0]) / current_group[0] <= 0.02:  # 2% tolerance
            current_group.append(level)
        else:
            grouped.append(sum(current_group) / len(current_group))
            current_group = [level]
    
    if current_group:
        grouped.append(sum(current_group) / len(current_group))
    
    return grouped

# ==================== ОСНОВНАЯ ЛОГИКА ====================
def analyze_signal(pair: str) -> Optional[Dict]:
    """Профессиональный анализ сигналов"""
    candles_1h = CANDLES.get_candles(pair, "1h")
    if len(candles_1h) < 100:
        return None
    
    closes = [c['c'] for c in candles_1h]
    current_price = closes[-1]
    
    # Рассчитываем индикаторы
    rsi_val = calculate_rsi(closes)
    trend = determine_trend(closes)
    supports, resistances = find_support_resistance_levels(candles_1h)
    macd_data = calculate_macd(closes)
    atr_val = atr(candles_1h)
    
    if rsi_val is None or atr_val is None:
        return None
    
    # Анализируем LONG
    long_signal = _analyze_long_signal(current_price, trend, rsi_val, macd_data, supports, candles_1h, atr_val)
    if long_signal:
        long_signal['pair'] = pair
        return long_signal
    
    # Анализируем SHORT
    short_signal = _analyze_short_signal(current_price, trend, rsi_val, macd_data, resistances, candles_1h, atr_val)
    if short_signal:
        short_signal['pair'] = pair
        return short_signal
    
    return None

def _analyze_long_signal(price: float, trend: str, rsi_val: float, macd_data: Optional[Tuple], 
                        supports: List[float], candles: List[dict], atr_val: float) -> Optional[Dict]:
    """Анализ LONG сигнала"""
    # Находим ближайшую качественную поддержку
    best_support = None
    for support in supports:
        if support < price:
            distance_pct = (price - support) / price
            if distance_pct <= 0.03:  # Не дальше 3%
                if best_support is None or support > best_support:
                    best_support = support
    
    if not best_support:
        return None
    
    confidence = 0
    reasons = []
    
    # 1. Уровень поддержки
    distance_pct = (price - best_support) / price
    if distance_pct <= 0.015:
        confidence += 25
        reasons.append("🎯 Сильная поддержка")
    elif distance_pct <= 0.025:
        confidence += 20
        reasons.append("✅ Уровень поддержки")
    
    # 2. RSI анализ
    if 30 <= rsi_val <= 45:
        confidence += 25
        reasons.append(f"📊 RSI для входа ({rsi_val:.1f})")
    elif 25 <= rsi_val < 30 or 45 < rsi_val <= 50:
        confidence += 15
        reasons.append(f"📈 RSI приемлемый ({rsi_val:.1f})")
    
    # 3. Тренд
    if trend == 'bullish':
        confidence += 20
        reasons.append("🟢 Бычий тренд")
    elif trend == 'neutral':
        confidence += 10
        reasons.append("⚪ Нейтральный тренд")
    
    # 4. MACD
    if macd_data and macd_data[0] > 0:
        confidence += 15
        reasons.append("📈 MACD положительный")
    
    # 5. Объёмы
    if _check_volume_support(candles, 'long'):
        confidence += 15
        reasons.append("💰 Объёмы подтверждают")
    
    if confidence >= MIN_CONFIDENCE:
        return _create_signal('LONG', price, best_support, confidence, reasons, atr_val)
    
    return None

def _analyze_short_signal(price: float, trend: str, rsi_val: float, macd_data: Optional[Tuple],
                         resistances: List[float], candles: List[dict], atr_val: float) -> Optional[Dict]:
    """Анализ SHORT сигнала"""
    # Находим ближайшее качественное сопротивление
    best_resistance = None
    for resistance in resistances:
        if resistance > price:
            distance_pct = (resistance - price) / price
            if distance_pct <= 0.03:  # Не дальше 3%
                if best_resistance is None or resistance < best_resistance:
                    best_resistance = resistance
    
    if not best_resistance:
        return None
    
    confidence = 0
    reasons = []
    
    # 1. Уровень сопротивления
    distance_pct = (best_resistance - price) / price
    if distance_pct <= 0.015:
        confidence += 25
        reasons.append("🎯 Сильное сопротивление")
    elif distance_pct <= 0.025:
        confidence += 20
        reasons.append("✅ Уровень сопротивления")
    
    # 2. RSI анализ
    if 55 <= rsi_val <= 70:
        confidence += 25
        reasons.append(f"📊 RSI для входа ({rsi_val:.1f})")
    elif 50 <= rsi_val < 55 or 70 < rsi_val <= 75:
        confidence += 15
        reasons.append(f"📈 RSI приемлемый ({rsi_val:.1f})")
    
    # 3. Тренд
    if trend == 'bearish':
        confidence += 20
        reasons.append("🔴 Медвежий тренд")
    elif trend == 'neutral':
        confidence += 10
        reasons.append("⚪ Нейтральный тренд")
    
    # 4. MACD
    if macd_data and macd_data[0] < 0:
        confidence += 15
        reasons.append("📉 MACD отрицательный")
    
    # 5. Объёмы
    if _check_volume_support(candles, 'short'):
        confidence += 15
        reasons.append("💰 Объёмы подтверждают")
    
    if confidence >= MIN_CONFIDENCE:
        return _create_signal('SHORT', price, best_resistance, confidence, reasons, atr_val)
    
    return None

def _check_volume_support(candles: List[dict], side: str) -> bool:
    """Проверка поддержки объёмами"""
    if len(candles) < 20:
        return False
    
    # Анализируем объёмы на последних свечах
    recent_candles = candles[-5:]
    prev_candles = candles[-10:-5]
    
    if not recent_candles or not prev_candles:
        return False
    
    # Средний объём
    recent_volume = sum(c['v'] for c in recent_candles) / len(recent_candles)
    prev_volume = sum(c['v'] for c in prev_candles) / len(prev_candles)
    
    # Для входа нужен повышенный объём
    return recent_volume > prev_volume * 0.8

def _create_signal(side: str, price: float, level: float, confidence: int, reasons: List[str], atr_val: float) -> Dict:
    """Создание сигнала с ATR-based TP/SL"""
    
    # Зона входа
    if side == 'LONG':
        entry_min = level * (1 - ENTRY_ZONE_PERCENT / 100)
        entry_max = level * (1 + ENTRY_ZONE_PERCENT / 100)
    else:
        entry_min = level * (1 - ENTRY_ZONE_PERCENT / 100)
        entry_max = level * (1 + ENTRY_ZONE_PERCENT / 100)
    
    # Расчёт TP/SL на основе ATR
    tp_sl = calculate_tp_sl(price, side, atr_val)
    
    position_size = _get_position_size(confidence)
    
    return {
        'side': side,
        'price': price,
        'entry_zone': (entry_min, entry_max),
        'stop_loss': tp_sl['stop_loss'],
        'take_profit_1': tp_sl['take_profit_1'],
        'take_profit_2': tp_sl['take_profit_2'],
        'take_profit_3': tp_sl['take_profit_3'],
        'score': confidence,
        'confidence': confidence,
        'reasons': reasons,
        'position_size': position_size,
        'sl_percent': tp_sl['sl_percent'],
        'tp1_percent': tp_sl['tp1_percent'],
        'tp2_percent': tp_sl['tp2_percent'],
        'tp3_percent': tp_sl['tp3_percent'],
        'atr': atr_val
    }

def _get_position_size(confidence: int) -> str:
    """Определение размера позиции"""
    if confidence >= 85:
        return "15-20% депо"
    elif confidence >= 75:
        return "10-12% депо"
    elif confidence >= 70:
        return "5-8% депо"
    else:
        return "3-5% депо"

# ==================== СОВМЕСТИМОСТЬ ====================
def quick_screen(pair: str) -> bool:
    """Быстрый скрининг - для совместимости"""
    candles = CANDLES.get_candles(pair, "1h")
    return len(candles) >= 50
