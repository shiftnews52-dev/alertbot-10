"""
config.py - Конфигурация для Системы 2 (Professional Analyzer)
ИСПРАВЛЕНО: Добавлены недостающие константы
"""
import os

# ==================== BOT SETTINGS ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_NAME = os.getenv("BOT_NAME", "Alpha Entry Bot")
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/support")

# ADMIN_IDS - можно задать через env или в коде
_admin_ids_env = os.getenv("ADMIN_IDS", "")
if _admin_ids_env:
    ADMIN_IDS = [int(x.strip()) for x in _admin_ids_env.split(",") if x.strip().isdigit()]
else:
    ADMIN_IDS = [
        7954736516, 390436725, 681419763,  # ← Замени на свой ID (узнай через @userinfobot)
    ]

# DB_PATH - единый для всех модулей
DB_PATH = os.getenv("DB_PATH", "/data/bot.db" if os.path.exists("/data") else "bot.db")

# ==================== CRYPTO BOT ====================
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "")

# ==================== TRADING SETTINGS ====================
# 15 дефолтных пар для анализа
DEFAULT_PAIRS = [
    "BTCUSDT",
    "ETHUSDT", 
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "DOTUSDT",
    "MATICUSDT",
    "LTCUSDT",
    "LINKUSDT",
    "AVAXUSDT",
    "UNIUSDT",
    "ATOMUSDT",
    "TONUSDT"
]

# ==================== ТАЙМФРЕЙМ (ФИКСИРОВАННЫЙ 1H) ====================
TIMEFRAME = "1h"  # Фиксированный часовой таймфрейм
CANDLE_TF = 3600  # 1 час в секундах
CHECK_INTERVAL = 300  # Проверять каждые 5 минут
MAX_CANDLES = 300  # Максимум свечей в истории (для 1h)

# ==================== INDICATORS ====================
EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 50
EMA_LONG_TREND = 200

RSI_PERIOD = 14
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 65

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

BB_PERIOD = 20
BB_STD = 2

# ==================== ИСПРАВЛЕНИЕ: Недостающие константы ====================
MIN_CONFIDENCE = 70        # Минимальный confidence для сигнала (используется в indicators.py)
ENTRY_ZONE_PERCENT = 1.0   # Зона входа ±1% (используется в indicators.py)
STOP_PERCENT = 2.0         # Стоп-лосс 2% от уровня (используется в indicators.py)

# ==================== FILTERS (УЛУЧШЕННЫЕ) ====================
MIN_SIGNAL_SCORE = 70      # Минимальный score для сигнала
MAX_SIGNALS_PER_DAY = 5    # Максимум сигналов в день на пару
SIGNAL_COOLDOWN = 21600    # 6 часов между сигналами одной пары (6 * 3600)

# Новые фильтры для качества
MIN_VOLUME_RATIO = 1.3     # Минимальное соотношение объёма (130% от среднего)
MIN_VOLATILITY = 0.003     # Минимальная волатильность (0.3%)
MAX_SPREAD_PERCENT = 0.5   # Максимальный спред для ликвидности (0.5%)

# ==================== OPTIMIZATION ====================
PRICE_CACHE_TTL = 30       # Кэш цен на 30 секунд
BATCH_SEND_SIZE = 30       # Отправлять группами по 30
BATCH_SEND_DELAY = 0.05    # Задержка между сообщениями

# ==================== IMAGES ====================
IMG_START = os.getenv("IMG_START", "")
IMG_ALERTS = os.getenv("IMG_ALERTS", "")
IMG_REF = os.getenv("IMG_REF", "")
IMG_PAYWALL = os.getenv("IMG_PAYWALL", "")
IMG_GUIDE = os.getenv("IMG_GUIDE", "")

# ==================== TAKE PROFIT / STOP LOSS ====================
TP1_PERCENT = 2.0  # TP1: 2% (R/R 2:1)
TP2_PERCENT = 4.0  # TP2: 4% (R/R 4:1)
TP3_PERCENT = 6.0  # TP3: 6% (R/R 6:1)
SL_PERCENT = 1.0   # SL: 1% (базовый)

# ==================== VALIDATION ====================
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not found in environment variables!")

if not CRYPTO_BOT_TOKEN:
    print("⚠️  Warning: CRYPTO_BOT_TOKEN not found - payments won't work")

if not ADMIN_IDS or ADMIN_IDS == [123456789]:
    print("⚠️  Warning: Please set your admin IDs in config.py or ADMIN_IDS env variable")

# ==================== STARTUP INFO ====================
print(f"✅ Config loaded (SYSTEM 2 - Professional Analyzer):")
print(f"   - Admin IDs: {ADMIN_IDS}")
print(f"   - DB Path: {DB_PATH}")
print(f"   - Default Pairs: {len(DEFAULT_PAIRS)} pairs")
print(f"   - Timeframe: {TIMEFRAME} (fixed)")
print(f"   - Check Interval: {CHECK_INTERVAL}s")
print(f"   - Max Signals/Day: {MAX_SIGNALS_PER_DAY}")
print(f"   - Signal Cooldown: {SIGNAL_COOLDOWN}s ({SIGNAL_COOLDOWN/3600:.1f}h)")
print(f"   - Min Confidence: {MIN_CONFIDENCE}")
print(f"   - Crypto Bot: {'Enabled' if CRYPTO_BOT_TOKEN else 'Disabled'}")
