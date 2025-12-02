#!/bin/bash

echo "🚀 =========================================="
echo "🚀 Starting Alpha Entry Bot (System 2)"
echo "🚀 Professional Analyzer + Multi-Timeframe"
echo "🚀 =========================================="

# Проверка переменных окружения
if [ -z "$BOT_TOKEN" ]; then
    echo "❌ Error: BOT_TOKEN not set!"
    exit 1
fi

if [ -z "$ADMIN_IDS" ]; then
    echo "⚠️  Warning: ADMIN_IDS not set"
fi

echo "✅ BOT_TOKEN: ****${BOT_TOKEN: -5}"
echo "✅ ADMIN_IDS: $ADMIN_IDS"

# ==================== МИГРАЦИЯ БАЗЫ ДАННЫХ ====================
echo ""
echo "🔧 =========================================="
echo "🔧 DATABASE MIGRATION"
echo "🔧 =========================================="
echo ""

# Запускаем миграцию для добавления колонки status
echo "⏳ Running database migration..."
python migrate_db.py

if [ $? -eq 0 ]; then
    echo "✅ Migration completed successfully"
else
    echo "⚠️  Migration warning (may be ok if table doesn't exist yet)"
fi

# Создание директории для данных (если нужна)
if [ ! -d "/data" ]; then
    mkdir -p ./data
    echo "✅ Created local data directory"
fi

# ==================== ИМПОРТ ИСТОРИЧЕСКИХ ДАННЫХ ====================
echo ""
echo "📊 =========================================="
echo "📊 IMPORTING HISTORICAL DATA"
echo "📊 =========================================="
echo ""

# Импорт данных для всех пар
echo "⏳ Importing candles for 15 pairs..."
echo "   This will take ~2-3 minutes..."
echo ""

python import_history.py all

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Historical data imported successfully!"
else
    echo ""
    echo "⚠️  Warning: Import failed, bot will collect data gradually"
fi

# ==================== ЗАПУСК БОТА ====================
echo ""
echo "🤖 =========================================="
echo "🤖 STARTING BOT"
echo "🤖 =========================================="
echo ""

python main.py

# Если бот упал, показать ошибку
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ =========================================="
    echo "❌ BOT CRASHED!"
    echo "❌ Check logs above for errors"
    echo "❌ =========================================="
    exit 1
fi
