"""
scheduler.py - Планировщик отправки сигналов
Запускает генерацию и отправку сигналов каждый час
"""
import asyncio
import logging
from datetime import datetime
from aiogram import Bot
from signal_generator import generate_signals, format_signal
from database import db_pool

logger = logging.getLogger(__name__)

# ==================== ОТПРАВКА СИГНАЛОВ ====================
async def send_signals_to_users(bot: Bot):
    """Генерация и отправка сигналов подписчикам"""
    try:
        logger.info("📡 Starting signal distribution...")
        
        # Генерируем сигналы
        signals = await generate_signals()
        
        if not signals:
            logger.info("No signals to send")
            return
        
        # Получаем пользователей с активными парами
        conn = await db_pool.acquire()
        try:
            cursor = await conn.execute("""
                SELECT DISTINCT user_id, language 
                FROM users 
                WHERE paid = 1
            """)
            paid_users = await cursor.fetchall()
        finally:
            await db_pool.release(conn)
        
        if not paid_users:
            logger.info("No paid users found")
            return
        
        # Отправляем сигналы
        total_sent = 0
        
        for signal in signals:
            symbol = signal["symbol"]
            
            for user_id, lang in paid_users:
                try:
                    # Проверяем есть ли пара у пользователя
                    conn = await db_pool.acquire()
                    try:
                        cursor = await conn.execute(
                            "SELECT pair FROM user_pairs WHERE user_id=? AND pair=?",
                            (user_id, symbol)
                        )
                        has_pair = await cursor.fetchone()
                    finally:
                        await db_pool.release(conn)
                    
                    if not has_pair:
                        continue
                    
                    # Форматируем и отправляем сигнал
                    lang_code = lang if lang else "ru"
                    text = format_signal(signal, lang_code)
                    
                    await bot.send_message(user_id, text, parse_mode="HTML")
                    total_sent += 1
                    
                    # Небольшая задержка чтобы не спамить
                    await asyncio.sleep(0.05)
                    
                except Exception as e:
                    logger.error(f"Error sending signal to {user_id}: {e}")
                    continue
        
        logger.info(f"✅ Sent {total_sent} signals to users")
        
    except Exception as e:
        logger.error(f"Error in send_signals_to_users: {e}")

# ==================== ПЛАНИРОВЩИК ====================
async def signal_scheduler(bot: Bot):
    """Планировщик - запускается каждый час"""
    logger.info("🕐 Signal scheduler started")
    
    while True:
        try:
            now = datetime.now()
            
            # Отправляем сигналы каждый час
            logger.info(f"⏰ Running hourly signal check at {now.strftime('%H:%M')}")
            await send_signals_to_users(bot)
            
            # Ждём до следующего часа
            # Вычисляем сколько секунд до начала следующего часа
            next_hour = now.replace(minute=0, second=0, microsecond=0)
            next_hour = next_hour.replace(hour=next_hour.hour + 1)
            
            sleep_seconds = (next_hour - now).total_seconds()
            
            logger.info(f"⏳ Next check in {sleep_seconds/60:.1f} minutes ({next_hour.strftime('%H:%M')})")
            await asyncio.sleep(sleep_seconds)
            
        except Exception as e:
            logger.error(f"Error in signal_scheduler: {e}")
            # При ошибке ждём 5 минут и пробуем снова
            await asyncio.sleep(300)

# ==================== РУЧНАЯ ОТПРАВКА ====================
async def send_test_signal(bot: Bot, user_id: int):
    """Отправить тестовый сигнал одному пользователю"""
    try:
        logger.info(f"Sending test signal to {user_id}...")
        
        # Генерируем сигналы
        signals = await generate_signals()
        
        if not signals:
            await bot.send_message(user_id, "❌ No signals found at the moment")
            return
        
        # Получаем язык пользователя
        conn = await db_pool.acquire()
        try:
            cursor = await conn.execute(
                "SELECT language FROM users WHERE id=?",
                (user_id,)
            )
            result = await cursor.fetchone()
            lang = result[0] if result else "ru"
        finally:
            await db_pool.release(conn)
        
        # Отправляем первый сигнал
        text = format_signal(signals[0], lang)
        await bot.send_message(user_id, text, parse_mode="HTML")
        
        logger.info(f"✅ Test signal sent to {user_id}")
        
    except Exception as e:
        logger.error(f"Error sending test signal: {e}")
