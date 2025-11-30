"""
main.py - Точка входа приложения
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher, executor

from config import BOT_TOKEN
from database import init_db
from handlers import setup_handlers
from tasks import price_collector, signal_analyzer
from pnl_tracker import pnl_tracker
from pnl_tasks import track_signals_pnl

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

async def on_startup(dp):
    """Запуск бота"""
    logger.info("Bot starting...")
    
    # Удаляем вебхук
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Инициализация БД
    await init_db()
    
    # Инициализация PnL трекера
    await pnl_tracker.init_db()
    logger.info("✅ PnL tracker initialized")
    
    # Регистрация обработчиков
    setup_handlers(dp)
    
    # Запуск фоновых задач
    loop = asyncio.get_event_loop()
    loop.create_task(price_collector(bot))
    loop.create_task(signal_analyzer(bot))
    loop.create_task(track_signals_pnl(bot))
    
    logger.info("✅ Bot started successfully!")

async def on_shutdown(dp):
    """Остановка бота"""
    logger.info("Bot shutting down...")
    await bot.close()

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)
