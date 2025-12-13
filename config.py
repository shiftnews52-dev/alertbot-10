"""
config.py - ОПТИМИЗИРОВАННЫЙ режим (8-12 сигналов в день)

ИЗМЕНЕНИЯ:
1. MIN_CONFIDENCE: 55 → 65 (строже)
2. SIGNAL_COOLDOWN: 2h → 4h
3. MAX_SIGNALS_PER_DAY: 5 → 3 (на пару)
4. GLOBAL_MAX_SIGNALS_PER_DAY: 20 → 12
5. Добавлен PRICE_DUPLICATE_THRESHOLD для антидублирования
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
        7954736516, 390436725, 681419763,
    ]

# DB_PATH - ВАЖНО: использовать /data для Persistent Disk на Render
# Проверяем существует ли /data (Persistent Disk на Render)
_data_dir = "/data" if os.path.exists("/data") else "."
DB_PATH = os.getenv("DB_PATH", f"{_data_dir}/bot.db")

# ==================== CRYPTO BOT ====================
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "")

# ==================== TRADING SETTINGS ====================
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

# ==================== ТАЙМФРЕЙМ ====================
TIMEFRAME = "1h"
CANDLE_TF = 3600
CHECK_INTERVAL = 300  # 5 минут
MAX_CANDLES = 300

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

# ==================== НАСТРОЙКИ СИГНАЛОВ ====================
MIN_CONFIDENCE = 65           # Было 55, теперь 65 (строже)
MIN_SIGNAL_SCORE = 65         # Синоним MIN_CONFIDENCE

ENTRY_ZONE_PERCENT = 1.0      # ±1.0%
STOP_PERCENT = 2.0            # 2.0%

# ==================== ЛИМИТЫ НА СИГНАЛЫ ====================
MAX_SIGNALS_PER_DAY = 3       # Было 5, теперь 3 на ОДНУ пару
GLOBAL_MAX_SIGNALS_PER_DAY = 12  # Было 20, теперь 12 всего
SIGNAL_COOLDOWN = 14400       # Было 7200 (2h), теперь 14400 (4 часа)

# ==================== АНТИДУБЛИРОВАНИЕ ====================
DUPLICATE_WINDOW = 4 * 3600   # 4 часа - не повторять сигнал для той же пары
PRICE_DUPLICATE_THRESHOLD = 0.03  # 3% - не повторять сигнал если цена в пределах 3%

# ==================== ФИЛЬТРЫ КАЧЕСТВА ====================
MIN_VOLUME_RATIO = 1.0        # Минимальный объём
MIN_VOLATILITY = 0.003        # Минимальная волатильность 0.3%
MAX_SPREAD_PERCENT = 0.5      # Максимальный спред 0.5%

# ==================== OPTIMIZATION ====================
PRICE_CACHE_TTL = 30
BATCH_SEND_SIZE = 30
BATCH_SEND_DELAY = 0.05

# ==================== IMAGES ====================
IMG_START = os.getenv("IMG_START", "")
IMG_ALERTS = os.getenv("IMG_ALERTS", "")
IMG_REF = os.getenv("IMG_REF", "")
IMG_PAYWALL = os.getenv("IMG_PAYWALL", "")
IMG_GUIDE = os.getenv("IMG_GUIDE", "")

# ==================== TAKE PROFIT / STOP LOSS (R:R) ====================
TP1_PERCENT = 2.0   # TP1: 2% (R/R 2:1)
TP2_PERCENT = 4.0   # TP2: 4% (R/R 4:1)
TP3_PERCENT = 6.0   # TP3: 6% (R/R 6:1)
SL_PERCENT = 1.0    # SL: 1%

# ==================== VALIDATION ====================
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not found!")

if not CRYPTO_BOT_TOKEN:
    print("⚠️  Warning: CRYPTO_BOT_TOKEN not found - payments disabled")

# ==================== STARTUP INFO ====================
print(f"✅ Config loaded (OPTIMIZED MODE):")
print(f"   - Admin IDs: {ADMIN_IDS}")
print(f"   - DB Path: {DB_PATH}")
print(f"   - Pairs: {len(DEFAULT_PAIRS)}")
print(f"   - Timeframe: {TIMEFRAME}")
print(f"   - Min Confidence: {MIN_CONFIDENCE}%")
print(f"   - Max Signals/Pair/Day: {MAX_SIGNALS_PER_DAY}")
print(f"   - Global Max Signals/Day: {GLOBAL_MAX_SIGNALS_PER_DAY}")
print(f"   - Signal Cooldown: {SIGNAL_COOLDOWN/3600:.0f}h")
print(f"   - Duplicate Window: {DUPLICATE_WINDOW/3600:.0f}h")
print(f"   - Price Duplicate Threshold: {PRICE_DUPLICATE_THRESHOLD*100:.0f}%")
print(f"   - Entry Zone: ±{ENTRY_ZONE_PERCENT}%")
