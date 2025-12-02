"""
main.py - Главный файл бота с поддержкой Crypto Bot вебхуков
"""
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiohttp import web

from config import BOT_TOKEN
from database import init_db, close_db
from handlers import setup_handlers
from crypto_payment import handle_crypto_webhook
from payment_handlers import setup_payment_handlers
from scheduler import signal_scheduler
from pnl_tracker import pnl_tracker
from pnl_tasks import track_signals_pnl

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ==================== ВЕБХУК ОБРАБОТЧИК ДЛЯ CRYPTO BOT ====================
async def crypto_webhook_handler(request):
    """Обработчик вебхуков от Crypto Bot"""
    try:
        signature = request.headers.get("Crypto-Pay-API-Signature", "")
        body = await request.read()
        
        logger.info(f"Received Crypto Bot webhook, signature: {signature[:20]}...")
        
        success = await handle_crypto_webhook(signature, body)
        
        if success:
            logger.info("Webhook processed successfully")
            return web.Response(text="OK")
        else:
            logger.warning("Webhook processing failed")
            return web.Response(text="ERROR", status=400)
    except Exception as e:
        logger.error(f"Webhook handler error: {e}")
        return web.Response(text="ERROR", status=500)

# ==================== HEALTHCHECK ====================
async def healthcheck_handler(request):
    """Healthcheck для Render"""
    return web.Response(text="OK")

# ==================== ЗАПУСК БОТА ====================
async def on_startup(dp):
    """Действия при запуске бота"""
    logger.info("Bot starting...")
    
    # Инициализация базы данных
    await init_db()
    logger.info("✅ Database initialized")
    
    # Инициализация PnL tracker
    await pnl_tracker.init_db()
    logger.info("✅ PnL tracker initialized")
    
    # Удаляем вебхук (для polling)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Webhook deleted")
    
    # Регистрируем обработчики
    setup_handlers(dp)
    logger.info("✅ Handlers registered")
    
    # Регистрируем платёжные обработчики
    setup_payment_handlers(dp, bot)
    logger.info("✅ Payment handlers registered")
    
    # Запускаем HTTP сервер для вебхуков
    app = web.Application()
    
    # Роуты
    app.router.add_post("/crypto_webhook", crypto_webhook_handler)
    app.router.add_get("/health", healthcheck_handler)
    app.router.add_get("/", healthcheck_handler)
    
    # Запуск сервера
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    logger.info(f"✅ HTTP server started on port {port}")
    logger.info(f"✅ Webhook endpoint: /crypto_webhook")
    logger.info("✅ Bot started successfully!")

async def on_shutdown(dp):
    """Действия при остановке бота"""
    logger.info("Bot shutting down...")
    
    # Закрываем соединения
    await close_db()
    await bot.close()
    await storage.close()
    
    logger.info("✅ Bot stopped")

# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================
async def main():
    """Главная функция"""
    try:
        # Запуск polling
        await on_startup(dp)
        
        # Запуск планировщика сигналов в фоне
        asyncio.create_task(signal_scheduler(bot))
        logger.info("✅ Signal scheduler started in background")
        
        # Запуск PnL трекера в фоне
        asyncio.create_task(track_signals_pnl(bot))
        logger.info("✅ PnL tracker started in background")
        
        # Запуск бота
        await dp.start_polling()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await on_shutdown(dp)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
