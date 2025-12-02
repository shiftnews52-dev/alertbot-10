"""
config.py - Конфигурация бота (ФИНАЛЬНАЯ ВЕРСИЯ)
"""
import os

# ==================== ТОКЕНЫ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "")

# ==================== АДМИНЫ ====================
# Можно задать в Environment Variables как: ADMIN_IDS=123456789,987654321
# Или изменить прямо здесь в коде
_admin_ids_env = os.getenv("ADMIN_IDS", "")
if _admin_ids_env:
    ADMIN_IDS = [int(id.strip()) for id in _admin_ids_env.split(",") if id.strip()]
else:
    ADMIN_IDS = [
        7954736516,390436725,681419763,  # ← Замени на свой ID (узнай через @userinfobot)
    ]

# ==================== ПОДДЕРЖКА ====================
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/SHIFTDM")  # Замени на свой канал

# ==================== ДЕФОЛТНЫЕ ПАРЫ ====================
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

# ==================== БАЗА ДАННЫХ ====================
# На Render используется /data (если существует), иначе локально bot.db
# ВАЖНО: Все модули импортируют DB_PATH отсюда для единой базы данных!
DB_PATH = os.getenv("DB_PATH", "/data/bot.db" if os.path.exists("/data") else "bot.db")

# ==================== КАРТИНКИ ====================
IMG_START = os.getenv("IMG_START", "")
IMG_ALERTS = os.getenv("IMG_ALERTS", "")
IMG_GUIDE = os.getenv("IMG_GUIDE", "")
IMG_PAYWALL = os.getenv("IMG_PAYWALL", "")
IMG_REF = os.getenv("IMG_REF", "")

# ==================== ПРОВЕРКА ====================
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not found in environment variables!")

if not CRYPTO_BOT_TOKEN:
    print("⚠️  Warning: CRYPTO_BOT_TOKEN not found - payments won't work")

if not ADMIN_IDS or ADMIN_IDS == [123456789]:
    print("⚠️  Warning: Please set your admin IDs in config.py or ADMIN_IDS env variable")

print(f"✅ Config loaded:")
print(f"   - Admin IDs: {ADMIN_IDS}")
print(f"   - DB Path: {DB_PATH}")
print(f"   - Default Pairs: {len(DEFAULT_PAIRS)} pairs")
print(f"   - Crypto Bot: {'Enabled' if CRYPTO_BOT_TOKEN else 'Disabled'}")
