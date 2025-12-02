"""
migrate_db.py - Миграция базы данных для добавления колонки status
"""
import asyncio
import aiosqlite
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# DB_PATH из переменной окружения или дефолт
DB_PATH = os.getenv("DB_PATH", "/opt/render/project/src/bot.db" if os.path.exists("/opt/render/project/src") else "bot.db")

async def migrate():
    """Добавление колонки status если её нет"""
    logger.info(f"Starting migration for database: {DB_PATH}")
    
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            # Проверяем существует ли таблица
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='active_signals'"
            )
            table_exists = await cursor.fetchone()
            
            if not table_exists:
                logger.info("Table 'active_signals' doesn't exist yet - will be created by bot")
                return
            
            # Проверяем есть ли колонка status
            cursor = await conn.execute("PRAGMA table_info(active_signals)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if 'status' in column_names:
                logger.info("✅ Column 'status' already exists - no migration needed")
                return
            
            # Добавляем колонку status
            logger.info("Adding 'status' column to active_signals...")
            await conn.execute(
                "ALTER TABLE active_signals ADD COLUMN status TEXT DEFAULT 'active'"
            )
            await conn.commit()
            logger.info("✅ Column 'status' added successfully!")
            
    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(migrate())
