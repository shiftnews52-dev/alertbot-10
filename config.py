"""
config.py - RARE/HIGH/MEDIUM система сигналов

ПОРОГИ CONFIDENCE:
- 🔥 RARE: ≥95% (без лимита)
- ⚡ HIGH: 80-94% (макс 3/день)
- 📊 MEDIUM: 70-79% (макс 8/день)
- <70% - игнор

COOLDOWN:
- 3 часа на пару
- Upgrade разрешён (MEDIUM→HIGH→RARE в cooldown)
"""
import os

# ==================== BOT SETTINGS ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_NAME = os.getenv("BOT_NAME", "Alpha Entry Bot")
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/SHIFTDM")

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
# Пороги confidence:
# RARE: ≥95% - без лимита
# HIGH: 80-94% - макс 3/день
# MEDIUM: 70-79% - макс 8/день
# <70% - игнор

RARE_CONFIDENCE = 95          # RARE порог
HIGH_CONFIDENCE = 80          # HIGH порог
MIN_CONFIDENCE = 70           # MEDIUM порог (минимум для отправки)
MIN_SIGNAL_SCORE = 70         # Синоним MIN_CONFIDENCE

ENTRY_ZONE_PERCENT = 1.0      # ±1.0%
STOP_PERCENT = 2.0            # 2.0%

# ==================== ЛИМИТЫ НА СИГНАЛЫ ====================
MAX_SIGNALS_PER_DAY = 3           # На ОДНУ пару
MAX_RARE_SIGNALS_PER_DAY = 999    # RARE - без лимита (фактически)
MAX_HIGH_SIGNALS_PER_DAY = 3      # HIGH - макс 3/день
MAX_MEDIUM_SIGNALS_PER_DAY = 8    # MEDIUM - макс 8/день

# ==================== COOLDOWN ====================
COOLDOWN_HOURS_PER_PAIR = 3       # 3 часа между сигналами одной пары
SIGNAL_COOLDOWN = COOLDOWN_HOURS_PER_PAIR * 3600  # В секундах

# ==================== РАСПРЕДЕЛЕНИЕ СИГНАЛОВ ПО ВРЕМЕНИ ====================
# Временные окна для HIGH сигналов (UTC)
HIGH_TIME_SLOTS = [
    (6, 10),   # Утро: 06:00-10:00 UTC (09:00-13:00 MSK)
    (11, 15),  # День: 11:00-15:00 UTC (14:00-18:00 MSK)
    (16, 21),  # Вечер: 16:00-21:00 UTC (19:00-00:00 MSK)
]

# Минимальные интервалы между сигналами одного типа (в минутах)
MIN_INTERVAL_RARE = 180      # 3 часа между RARE
MIN_INTERVAL_HIGH = 180      # 3 часа между HIGH  
MIN_INTERVAL_MEDIUM = 90     # 1.5 часа между MEDIUM

# Время жизни сигнала в очереди (минуты) - после этого считается "протухшим"
SIGNAL_QUEUE_TTL = 60        # 1 час

# Максимальное отклонение цены для актуальности сигнала (%)
SIGNAL_PRICE_TOLERANCE = 2.0  # 2% от entry price

# ==================== ПРОМО И НАПОМИНАНИЯ ====================
# Напоминание за N дней до истечения
REMINDER_DAYS_BEFORE = 2

# Интервал между промо-сообщениями для неподписанных (часы)
PROMO_INTERVAL_HOURS = 48    # Раз в 2 дня

# Скидка на продление (%)
RENEWAL_DISCOUNT_PERCENT = 25

# Час отправки напоминаний (UTC) - чтобы не будить ночью
NOTIFICATION_HOUR_UTC = 10   # 10:00 UTC = 13:00 MSK

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
print(f"✅ Config loaded (RARE/HIGH/MEDIUM + Time Distribution):")
print(f"   - Admin IDs: {ADMIN_IDS}")
print(f"   - DB Path: {DB_PATH}")
print(f"   - Pairs: {len(DEFAULT_PAIRS)}")
print(f"   - 🔥 RARE: ≥{RARE_CONFIDENCE}% (no limit)")
print(f"   - ⚡ HIGH: {HIGH_CONFIDENCE}-{RARE_CONFIDENCE-1}% (max {MAX_HIGH_SIGNALS_PER_DAY}/day, 3 time slots)")
print(f"   - 📊 MEDIUM: {MIN_CONFIDENCE}-{HIGH_CONFIDENCE-1}% (max {MAX_MEDIUM_SIGNALS_PER_DAY}/day)")
print(f"   - Cooldown: {COOLDOWN_HOURS_PER_PAIR}h per pair")
print(f"   - Intervals: RARE={MIN_INTERVAL_RARE}min, HIGH={MIN_INTERVAL_HIGH}min, MEDIUM={MIN_INTERVAL_MEDIUM}min")
print(f"   - HIGH slots (UTC): {HIGH_TIME_SLOTS}")
print(f"   - Queue TTL: {SIGNAL_QUEUE_TTL}min")
