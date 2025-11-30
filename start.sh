#!/bin/bash
# Alpha Entry Bot - Start script (1H ONLY)
# Автоматический импорт исторических данных

set -e

echo "============================================================"
echo "🚀 Alpha Entry Bot - Starting (1H Timeframe)"
echo "============================================================"
echo ""

# ==================== ПРОВЕРКИ ====================
echo "🔍 Pre-flight checks..."
echo ""

# Python версия
echo "🐍 Python version:"
python --version
echo ""

# Переменные окружения
if [ -z "$BOT_TOKEN" ]; then
    echo "❌ ERROR: BOT_TOKEN not set!"
    echo "   Set it in environment or .env file"
    exit 1
fi

if [ -z "$ADMIN_IDS" ]; then
    echo "❌ ERROR: ADMIN_IDS not set!"
    echo "   Set it in environment or .env file"
    exit 1
fi

echo "✅ BOT_TOKEN: Set"
echo "✅ ADMIN_IDS: Set"
echo "✅ TIMEFRAME: 1h (fixed)"
echo ""

# ==================== ИМПОРТ ИСТОРИИ ====================
echo "============================================================"
echo "📥 Importing historical data (1h timeframe)"
echo "============================================================"
echo ""

if [ -f "import_history.py" ]; then
    echo "📊 Importing 300 hourly candles for default pairs..."
    
    if python import_history.py all 300; then
        echo ""
        echo "✅ Historical data imported successfully!"
    else
        echo ""
        echo "⚠️  Warning: Import failed, but continuing..."
        echo "   Bot will work but needs time to collect data (~4 hours)"
    fi
else
    echo "⚠️  Warning: import_history.py not found"
    echo "   Bot will start but needs time to collect data"
fi

echo ""

# ==================== ЗАПУСК БОТА ====================
echo "============================================================"
echo "🤖 Starting main bot..."
echo "============================================================"
echo ""

# Экспорт переменных
export BOT_TOKEN
export ADMIN_IDS
export SUPPORT_URL=${SUPPORT_URL:-https://t.me/support}
export BOT_NAME=${BOT_NAME:-Alpha Entry Bot}

# Запуск
python main.py
