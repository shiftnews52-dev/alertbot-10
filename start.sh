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

# ==================== ОЧИСТКА СТАРОЙ БД ====================
echo ""
echo "🧹 =========================================="
echo "🧹 DATABASE CLEANUP"
echo "🧹 =========================================="
echo ""

# Путь к БД
DB_PATH="${DB_PATH:-/opt/render/project/src/bot.db}"
echo "📍 DB Path: $DB_PATH"

# Проверяем существует ли БД
if [ -f "$DB_PATH" ]; then
    echo "⚠️  Old database found!"
    echo "🗑️  Removing old database to ensure clean schema..."
    
    # Удаляем старую БД и все связанные файлы
    rm -f "$DB_PATH"
    rm -f "${DB_PATH}-shm"
    rm -f "${DB_PATH}-wal"
    rm -f "${DB_PATH}-journal"
    
    if [ ! -f "$DB_PATH" ]; then
        echo "✅ Old database removed successfully!"
    else
        echo "❌ Failed to remove old database"
    fi
else
    echo "✅ No old database found - will create fresh one"
fi

echo ""

# ==================== МИГРАЦИЯ БАЗЫ ДАННЫХ ====================
echo "🔧 =========================================="
echo "🔧 DATABASE MIGRATION"
echo "🔧 =========================================="
echo ""

# Запускаем миграцию (на всякий случай)
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
```

#### **5. Внизу нажми "Commit changes"**

#### **6. Commit message:**
```
🗑️ Add auto DB cleanup on startup
```

#### **7. Нажми "Commit changes"**

---

## ✅ **ПОСЛЕ COMMIT:**

**Render автоматически:**
1. Обнаружит изменения (30 сек)
2. Запустит новый build (1 мин)
3. **Удалит старую БД** 🗑️ ← ВАЖНО!
4. Создаст новую БД с правильной схемой
5. Запустит бота ✅

**Общее время: ~5 минут**

---

## 📊 **ОЖИДАЕМЫЕ ЛОГИ:**
```
🧹 DATABASE CLEANUP          ← НОВОЕ!
📍 DB Path: /opt/render/project/src/bot.db
⚠️  Old database found!
🗑️  Removing old database to ensure clean schema...
✅ Old database removed successfully!  ← БД УДАЛЕНА!

🔧 DATABASE MIGRATION
✅ Migration completed successfully

📊 IMPORTING HISTORICAL DATA
✅ Historical data imported successfully!

🤖 STARTING BOT
✅ Database initialized
✅ PnL tracker initialized  ← БЕЗ ОШИБКИ!
✅ Bot started successfully!
Start polling.  ← РАБОТАЕТ!
