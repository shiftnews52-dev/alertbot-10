"""
signal_generator.py - Генератор торговых сигналов
Анализирует крипто пары и отправляет качественные сигналы
"""
import asyncio
import logging
from datetime import datetime, timedelta
import httpx
from typing import List, Dict, Optional
import statistics

logger = logging.getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ ====================
BINANCE_API = "https://api.binance.com/api/v3"

# Пары для анализа
TRADING_PAIRS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
    "XRPUSDT", "DOGEUSDT", "DOTUSDT", "MATICUSDT", "LTCUSDT",
    "LINKUSDT", "AVAXUSDT", "UNIUSDT", "ATOMUSDT", "TONUSDT"
]

# Параметры сигналов
MIN_SCORE = 85  # Минимальный score для сигнала
MAX_SIGNALS_PER_DAY = 3  # Максимум сигналов в день
MIN_VOLUME_24H = 50_000_000  # Минимальный объём за 24ч ($50M)

# Параметры индикаторов
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
BB_PERIOD = 20
BB_STD = 2

# Счётчик отправленных сигналов
daily_signals_sent = {}

# ==================== ПОЛУЧЕНИЕ ДАННЫХ ====================
async def get_klines(symbol: str, interval: str = "1h", limit: int = 100) -> Optional[List]:
    """Получить свечи с Binance"""
    try:
        url = f"{BINANCE_API}/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Binance API error for {symbol}: {response.status_code}")
                return None
                
    except Exception as e:
        logger.error(f"Error fetching klines for {symbol}: {e}")
        return None

async def get_24h_ticker(symbol: str) -> Optional[Dict]:
    """Получить 24ч статистику"""
    try:
        url = f"{BINANCE_API}/ticker/24hr"
        params = {"symbol": symbol}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"24h ticker error for {symbol}: {response.status_code}")
                return None
                
    except Exception as e:
        logger.error(f"Error fetching 24h ticker for {symbol}: {e}")
        return None

# ==================== ТЕХНИЧЕСКИЙ АНАЛИЗ ====================
def calculate_ema(prices: List[float], period: int) -> float:
    """Вычислить EMA"""
    if len(prices) < period:
        return prices[-1]
    
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    
    return ema

def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Вычислить RSI"""
    if len(prices) < period + 1:
        return 50.0
    
    changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [max(0, change) for change in changes[-period:]]
    losses = [abs(min(0, change)) for change in changes[-period:]]
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: int = 2) -> Dict:
    """Вычислить Bollinger Bands"""
    if len(prices) < period:
        return {"upper": prices[-1], "middle": prices[-1], "lower": prices[-1]}
    
    recent_prices = prices[-period:]
    middle = sum(recent_prices) / period
    std = statistics.stdev(recent_prices)
    
    return {
        "upper": middle + (std_dev * std),
        "middle": middle,
        "lower": middle - (std_dev * std)
    }

def calculate_macd(prices: List[float]) -> Dict:
    """Вычислить MACD"""
    if len(prices) < 26:
        return {"macd": 0, "signal": 0, "histogram": 0}
    
    ema_12 = calculate_ema(prices, 12)
    ema_26 = calculate_ema(prices, 26)
    macd = ema_12 - ema_26
    
    # Signal line (EMA of MACD)
    macd_values = []
    for i in range(26, len(prices)):
        ema12 = calculate_ema(prices[:i+1], 12)
        ema26 = calculate_ema(prices[:i+1], 26)
        macd_values.append(ema12 - ema26)
    
    signal = calculate_ema(macd_values, 9) if len(macd_values) >= 9 else macd
    histogram = macd - signal
    
    return {
        "macd": macd,
        "signal": signal,
        "histogram": histogram
    }

# ==================== АНАЛИЗ И СКОРИНГ ====================
async def analyze_pair(symbol: str) -> Optional[Dict]:
    """Анализировать пару и вернуть сигнал"""
    try:
        # Получаем данные
        klines = await get_klines(symbol, "1h", 100)
        ticker_24h = await get_24h_ticker(symbol)
        
        if not klines or not ticker_24h:
            return None
        
        # Проверка объёма
        volume_24h = float(ticker_24h.get("quoteVolume", 0))
        if volume_24h < MIN_VOLUME_24H:
            logger.debug(f"{symbol}: Volume too low (${volume_24h:,.0f})")
            return None
        
        # Извлекаем цены закрытия
        closes = [float(k[4]) for k in klines]
        current_price = closes[-1]
        
        # Вычисляем индикаторы
        ema_fast = calculate_ema(closes, EMA_FAST)
        ema_slow = calculate_ema(closes, EMA_SLOW)
        rsi = calculate_rsi(closes, RSI_PERIOD)
        bb = calculate_bollinger_bands(closes, BB_PERIOD, BB_STD)
        macd_data = calculate_macd(closes)
        
        # Вычисляем ATR для волатильности
        highs = [float(k[2]) for k in klines[-14:]]
        lows = [float(k[3]) for k in klines[-14:]]
        ranges = [highs[i] - lows[i] for i in range(len(highs))]
        atr = sum(ranges) / len(ranges)
        atr_percent = (atr / current_price) * 100
        
        # ==================== СКОРИНГ ====================
        score = 0
        reasons = []
        signal_type = None
        
        # 1. EMA Trend (20 points)
        if ema_fast > ema_slow:
            score += 20
            signal_type = "LONG"
            reasons.append("🟢 EMA бычий тренд")
        elif ema_fast < ema_slow:
            score += 20
            signal_type = "SHORT"
            reasons.append("🔴 EMA медвежий тренд")
        
        # 2. RSI (20 points)
        if signal_type == "LONG" and 30 < rsi < 50:
            score += 20
            reasons.append(f"📊 RSI в зоне покупки ({rsi:.1f})")
        elif signal_type == "SHORT" and 50 < rsi < 70:
            score += 20
            reasons.append(f"📊 RSI в зоне продажи ({rsi:.1f})")
        elif signal_type == "LONG" and rsi < 30:
            score += 15
            reasons.append(f"💎 RSI перепродан ({rsi:.1f})")
        elif signal_type == "SHORT" and rsi > 70:
            score += 15
            reasons.append(f"💎 RSI перекуплен ({rsi:.1f})")
        
        # 3. Bollinger Bands (15 points)
        if signal_type == "LONG" and current_price < bb["lower"]:
            score += 15
            reasons.append("📉 Цена у нижней BB")
        elif signal_type == "SHORT" and current_price > bb["upper"]:
            score += 15
            reasons.append("📈 Цена у верхней BB")
        
        # 4. MACD (15 points)
        if signal_type == "LONG" and macd_data["histogram"] > 0:
            score += 15
            reasons.append("✅ MACD бычий")
        elif signal_type == "SHORT" and macd_data["histogram"] < 0:
            score += 15
            reasons.append("✅ MACD медвежий")
        
        # 5. Объём (15 points)
        current_volume = float(klines[-1][5])
        avg_volume = sum([float(k[5]) for k in klines[-20:]]) / 20
        if current_volume > avg_volume * 1.5:
            score += 15
            reasons.append("🔊 Высокий объём")
        
        # 6. Волатильность (15 points)
        if 1.5 < atr_percent < 5:
            score += 15
            reasons.append(f"⚡ Хорошая волатильность ({atr_percent:.1f}%)")
        
        # Проверяем минимальный score
        if score < MIN_SCORE:
            logger.debug(f"{symbol}: Score too low ({score}/100)")
            return None
        
        # ==================== УРОВНИ TP/SL ====================
        if signal_type == "LONG":
            stop_loss = current_price - (atr * 1.5)
            take_profit_1 = current_price + (atr * 1.0)
            take_profit_2 = current_price + (atr * 2.0)
            take_profit_3 = current_price + (atr * 3.0)
        else:  # SHORT
            stop_loss = current_price + (atr * 1.5)
            take_profit_1 = current_price - (atr * 1.0)
            take_profit_2 = current_price - (atr * 2.0)
            take_profit_3 = current_price - (atr * 3.0)
        
        # Формируем сигнал
        signal = {
            "symbol": symbol,
            "type": signal_type,
            "score": score,
            "price": current_price,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "take_profit_3": take_profit_3,
            "reasons": reasons,
            "indicators": {
                "rsi": round(rsi, 1),
                "ema_fast": round(ema_fast, 8),
                "ema_slow": round(ema_slow, 8),
                "atr_percent": round(atr_percent, 2)
            },
            "timestamp": datetime.now()
        }
        
        logger.info(f"✅ Signal found: {symbol} {signal_type} (score: {score}/100)")
        return signal
        
    except Exception as e:
        logger.error(f"Error analyzing {symbol}: {e}")
        return None

# ==================== ГЕНЕРАЦИЯ СИГНАЛОВ ====================
async def generate_signals() -> List[Dict]:
    """Сгенерировать сигналы для всех пар"""
    logger.info("🔍 Starting signal generation...")
    
    # Проверяем дневной лимит
    today = datetime.now().date()
    if today not in daily_signals_sent:
        daily_signals_sent[today] = 0
    
    if daily_signals_sent[today] >= MAX_SIGNALS_PER_DAY:
        logger.info(f"Daily limit reached ({MAX_SIGNALS_PER_DAY} signals)")
        return []
    
    # Анализируем все пары
    tasks = [analyze_pair(symbol) for symbol in TRADING_PAIRS]
    results = await asyncio.gather(*tasks)
    
    # Фильтруем и сортируем сигналы
    signals = [s for s in results if s is not None]
    signals.sort(key=lambda x: x["score"], reverse=True)
    
    # Ограничиваем количество сигналов
    remaining = MAX_SIGNALS_PER_DAY - daily_signals_sent[today]
    signals = signals[:remaining]
    
    if signals:
        daily_signals_sent[today] += len(signals)
        logger.info(f"📊 Generated {len(signals)} signals (total today: {daily_signals_sent[today]})")
    else:
        logger.info("No quality signals found")
    
    return signals

# ==================== ФОРМАТИРОВАНИЕ СИГНАЛА ====================
def format_signal(signal: Dict, lang: str = "ru") -> str:
    """Форматировать сигнал для отправки"""
    symbol = signal["symbol"]
    signal_type = signal["type"]
    score = signal["score"]
    price = signal["price"]
    sl = signal["stop_loss"]
    tp1 = signal["take_profit_1"]
    tp2 = signal["take_profit_2"]
    tp3 = signal["take_profit_3"]
    
    # Эмодзи для типа
    emoji = "🟢" if signal_type == "LONG" else "🔴"
    
    if lang == "en":
        text = f"{emoji} <b>{signal_type} {symbol}</b>\n\n"
        text += f"💰 <b>Entry:</b> ${price:.8g}\n"
        text += f"🛑 <b>Stop Loss:</b> ${sl:.8g}\n\n"
        text += f"🎯 <b>Take Profits:</b>\n"
        text += f"• TP1: ${tp1:.8g} ({abs((tp1-price)/price*100):.1f}%)\n"
        text += f"• TP2: ${tp2:.8g} ({abs((tp2-price)/price*100):.1f}%)\n"
        text += f"• TP3: ${tp3:.8g} ({abs((tp3-price)/price*100):.1f}%)\n\n"
        text += f"📊 <b>Score:</b> {score}/100\n\n"
        text += f"<b>Analysis:</b>\n"
        text += "\n".join(signal["reasons"])
        text += f"\n\n⏰ {signal['timestamp'].strftime('%H:%M UTC')}"
    else:
        text = f"{emoji} <b>{signal_type} {symbol}</b>\n\n"
        text += f"💰 <b>Вход:</b> ${price:.8g}\n"
        text += f"🛑 <b>Стоп:</b> ${sl:.8g}\n\n"
        text += f"🎯 <b>Цели:</b>\n"
        text += f"• TP1: ${tp1:.8g} ({abs((tp1-price)/price*100):.1f}%)\n"
        text += f"• TP2: ${tp2:.8g} ({abs((tp2-price)/price*100):.1f}%)\n"
        text += f"• TP3: ${tp3:.8g} ({abs((tp3-price)/price*100):.1f}%)\n\n"
        text += f"📊 <b>Оценка:</b> {score}/100\n\n"
        text += f"<b>Анализ:</b>\n"
        text += "\n".join(signal["reasons"])
        text += f"\n\n⏰ {signal['timestamp'].strftime('%H:%M UTC')}"
    
    return text

# ==================== ТЕСТИРОВАНИЕ ====================
async def test_signal_generator():
    """Тест генератора сигналов"""
    logger.info("Testing signal generator...")
    
    signals = await generate_signals()
    
    print(f"\n{'='*60}")
    print(f"Найдено сигналов: {len(signals)}")
    print(f"{'='*60}\n")
    
    for signal in signals:
        print(format_signal(signal, "ru"))
        print(f"\n{'='*60}\n")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_signal_generator())
