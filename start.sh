#!/bin/bash

echo "🚀 =========================================="
echo "🚀 Starting Alpha Entry Bot (System 2)"
echo "🚀 Professional Analyzer + PnL Tracker"
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

# ==================== ОПРЕДЕЛЕНИЕ ПУТИ К БД ====================
echo ""
echo "🧹 =========================================="
echo "🧹 DATABASE SETUP"
echo "🧹 =========================================="
echo ""

# Автоопределение пути к БД
# Если /data существует (Persistent Disk) - используем его
if [ -d "/data" ]; then
    DB_PATH="/data/bot.db"
    echo "✅ Persistent Disk found at /data"
else
    DB_PATH="${DB_PATH:-/opt/render/project/src/bot.db}"
    echo "⚠️  No Persistent Disk - using ephemeral storage"
fi

export DB_PATH
echo "📍 DB Path: $DB_PATH"

# НЕ удаляем БД если она на Persistent Disk!
if [ -f "$DB_PATH" ]; then
    if [[ "$DB_PATH" == /data/* ]]; then
        echo "✅ Existing database found on Persistent Disk - keeping it!"
    else
        echo "⚠️  Database in ephemeral storage - will be recreated"
    fi
else
    echo "📝 No database found - will create new one"
fi

echo ""

# ==================== МИГРАЦИЯ БАЗЫ ДАННЫХ ====================
echo "🔧 =========================================="
echo "🔧 DATABASE MIGRATION"
echo "🔧 =========================================="
echo ""

# Запускаем миграцию
echo "⏳ Running database migration..."
python migrate_db.py

if [ $? -eq 0 ]; then
    echo "✅ Migration completed successfully"
else
    echo "⚠️  Migration warning (may be ok if table doesn't exist yet)"
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
