"""
config.py - PRO/FREE система сигналов

PRO доступ:
- 🔥 RARE: ≥95% — макс 1/день
- ⚡ HIGH: 80-94% — макс 2/день
- Без задержки, полная информация

FREE доступ (постоянный):
- 📊 MEDIUM: 70-79% — макс 1/день
- Задержка 45 минут
- Скрыты TP2, TP3, Stop Loss

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
# RARE: ≥95% - PRO only, макс 1/день
# HIGH: 80-94% - PRO only, макс 2/день
# MEDIUM: 70-79% - FREE (с задержкой), PRO сразу
# <70% - игнор

RARE_CONFIDENCE = 95          # RARE порог
HIGH_CONFIDENCE = 80          # HIGH порог
MIN_CONFIDENCE = 70           # MEDIUM порог (минимум для отправки)
MIN_SIGNAL_SCORE = 70         # Синоним MIN_CONFIDENCE

ENTRY_ZONE_PERCENT = 1.0      # ±1.0%
STOP_PERCENT = 2.0            # 2.0%

# ==================== ЛИМИТЫ НА СИГНАЛЫ (НОВАЯ ЛОГИКА) ====================
# PRO: видит RARE + HIGH + MEDIUM сразу
# FREE: видит только MEDIUM с задержкой

MAX_SIGNALS_PER_DAY = 3           # На ОДНУ пару
MAX_RARE_SIGNALS_PER_DAY = 1      # 🔥 RARE — макс 1/день
MAX_HIGH_SIGNALS_PER_DAY = 2      # ⚡ HIGH — макс 2/день
MAX_MEDIUM_SIGNALS_PER_DAY = 1    # 📊 MEDIUM — макс 1/день (для FREE)

# ==================== FREE ДОСТУП ====================
FREE_SIGNAL_DELAY = 45 * 60       # Задержка 45 минут (в секундах)
FREE_MAX_SIGNALS_PER_DAY = 1      # FREE видит макс 1 сигнал/день
FREE_SHOW_TP1 = True              # FREE видит TP1
FREE_SHOW_TP2 = False             # FREE НЕ видит TP2
FREE_SHOW_TP3 = False             # FREE НЕ видит TP3
FREE_SHOW_SL = False              # FREE НЕ видит Stop Loss

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

# ==================== SIGNAL TRACKING (UPDATES) ====================
# Автоматическое отслеживание: вход, TP1, TP2, TP3, SL
TRACKING_ENABLED = True
TRACKING_CHECK_INTERVAL = 60      # Проверка каждые 60 секунд
ENTRY_ACTIVATION_TOLERANCE = 0.5  # Вход активирован если цена в пределах 0.5%

# ==================== "НЕТ СИГНАЛОВ" СООБЩЕНИЕ ====================
NO_SIGNALS_MESSAGE_ENABLED = True
NO_SIGNALS_HOUR_UTC = 20          # Отправлять в 20:00 UTC если не было сигналов

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

# ==================== РЕФЕРАЛЬНАЯ СИСТЕМА ====================
# 2-уровневая: Manager → Partner → User
# Бонусы с ПЕРВОЙ оплаты ($20)
REFERRAL_BONUS_PARTNER = 10.0    # Partner (владелец канала) получает $10
REFERRAL_BONUS_MANAGER = 3.0     # Manager (привёл партнёра) получает $3
# Остальное ($7) - владельцу бота

# Бонусы с продлений
RENEWAL_BONUS_PARTNER = 0.0      # 0 за продление
RENEWAL_BONUS_MANAGER = 0.0      # 0 за продление

MIN_WITHDRAWAL = 20.0            # Минимум для вывода

# ==================== STARTUP INFO ====================
print(f"✅ Config loaded (PRO/FREE система):")
print(f"   - Admin IDs: {ADMIN_IDS}")
print(f"   - DB Path: {DB_PATH}")
print(f"   - Pairs: {len(DEFAULT_PAIRS)}")
print(f"   - 🔥 RARE: ≥{RARE_CONFIDENCE}% (PRO, max {MAX_RARE_SIGNALS_PER_DAY}/day)")
print(f"   - ⚡ HIGH: {HIGH_CONFIDENCE}-{RARE_CONFIDENCE-1}% (PRO, max {MAX_HIGH_SIGNALS_PER_DAY}/day)")
print(f"   - 📊 MEDIUM: {MIN_CONFIDENCE}-{HIGH_CONFIDENCE-1}% (FREE delayed {FREE_SIGNAL_DELAY//60}min, max {FREE_MAX_SIGNALS_PER_DAY}/day)")
print(f"   - Cooldown: {COOLDOWN_HOURS_PER_PAIR}h per pair")
print(f"   - Tracking: {'ON' if TRACKING_ENABLED else 'OFF'}")
