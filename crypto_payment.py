"""
crypto_payment.py - Интеграция с Crypto Bot для приёма платежей
Документация: https://help.crypt.bot/crypto-pay-api
"""
import os
import hashlib
import hmac
import json
import logging
from typing import Optional, Dict
import httpx
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ ====================
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "")  # Токен из @CryptoBot
CRYPTO_BOT_API = "https://pay.crypt.bot/api"

# ==================== ТАРИФНЫЕ ПЛАНЫ ====================
SUBSCRIPTION_PLANS = {
    "1m": {
        "name": "1 месяц",
        "name_en": "1 Month",
        "price": 20.00,
        "duration_days": 30,
        "discount": 0,
        "emoji": "📅"
    },
    "3m": {
        "name": "3 месяца",
        "name_en": "3 Months", 
        "price": 50.00,
        "duration_days": 90,
        "discount": 17,  # (60-50)/60 * 100 = 17%
        "emoji": "📆",
        "badge": "🔥 -17%"
    },
    "6m": {
        "name": "6 месяцев",
        "name_en": "6 Months",
        "price": 90.00,
        "duration_days": 180,
        "discount": 25,  # (120-90)/120 * 100 = 25%
        "emoji": "📊",
        "badge": "💎 -25%"
    },
    "12m": {
        "name": "12 месяцев",
        "name_en": "12 Months",
        "price": 140.00,
        "duration_days": 365,
        "discount": 42,  # (240-140)/240 * 100 = 42%
        "emoji": "👑",
        "badge": "🚀 -42%"
    }
}

# ==================== CRYPTO BOT API ====================
class CryptoPayAPI:
    """Класс для работы с Crypto Bot API"""
    
    def __init__(self, token: str = CRYPTO_BOT_TOKEN):
        self.token = token
        self.api_url = CRYPTO_BOT_API
        self.headers = {
            "Crypto-Pay-API-Token": token
        }
    
    async def create_invoice(
        self,
        amount: float,
        currency: str = "USDT",
        description: str = "",
        payload: str = "",
        allow_comments: bool = False,
        allow_anonymous: bool = False
    ) -> Optional[Dict]:
        """
        Создать инвойс для оплаты
        
        Args:
            amount: Сумма в USD
            currency: Валюта (USDT, TON, BTC, ETH и др.)
            description: Описание платежа
            payload: Данные для идентификации (user_id:plan_id)
            allow_comments: Разрешить комментарии
            allow_anonymous: Разрешить анонимную оплату
        
        Returns:
            {
                'invoice_id': 12345,
                'pay_url': 'https://t.me/CryptoBot?start=...',
                'amount': '20.00',
                'currency': 'USDT'
            }
        """
        try:
            async with httpx.AsyncClient() as client:
                data = {
                    "amount": str(amount),
                    "currency_type": "fiat",  # fiat для USD
                    "fiat": "USD",
                    "accepted_assets": currency,  # Какие криптовалюты принимать
                    "description": description,
                    "payload": payload,
                    "allow_comments": allow_comments,
                    "allow_anonymous": allow_anonymous
                }
                
                response = await client.post(
                    f"{self.api_url}/createInvoice",
                    headers=self.headers,
                    json=data,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("ok"):
                        invoice = result["result"]
                        logger.info(f"Invoice created: {invoice['invoice_id']}")
                        return {
                            "invoice_id": invoice["invoice_id"],
                            "pay_url": invoice["pay_url"],
                            "amount": invoice["amount"],
                            "currency": invoice["asset"]
                        }
                    else:
                        logger.error(f"Crypto Bot API error: {result.get('error')}")
                else:
                    logger.error(f"HTTP error: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Create invoice error: {e}")
        
        return None
    
    async def get_invoice(self, invoice_id: int) -> Optional[Dict]:
        """
        Получить информацию об инвойсе
        
        Returns:
            {
                'invoice_id': 12345,
                'status': 'paid' | 'active' | 'expired',
                'amount': '20.00',
                'paid_at': 1234567890
            }
        """
        try:
            async with httpx.AsyncClient() as client:
                params = {"invoice_ids": invoice_id}
                
                response = await client.get(
                    f"{self.api_url}/getInvoices",
                    headers=self.headers,
                    params=params,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("ok") and result["result"]["items"]:
                        return result["result"]["items"][0]
                        
        except Exception as e:
            logger.error(f"Get invoice error: {e}")
        
        return None
    
    async def verify_webhook(self, signature: str, body: bytes) -> bool:
        """
        Проверить подпись вебхука от Crypto Bot
        
        Args:
            signature: Заголовок Crypto-Pay-API-Signature
            body: Тело запроса (байты)
        
        Returns:
            True если подпись валидна
        """
        try:
            secret = hashlib.sha256(self.token.encode()).digest()
            check_string = body
            hmac_hash = hmac.new(secret, check_string, hashlib.sha256).hexdigest()
            return hmac_hash == signature
        except Exception as e:
            logger.error(f"Webhook verification error: {e}")
            return False

# Глобальный экземпляр API
crypto_api = CryptoPayAPI()

# ==================== HELPER FUNCTIONS ====================
async def create_payment_invoice(user_id: int, plan_id: str, lang: str = "ru") -> Optional[Dict]:
    """
    Создать инвойс для оплаты подписки
    
    Args:
        user_id: ID пользователя Telegram
        plan_id: ID тарифного плана (1m, 3m, 6m, 12m)
        lang: Язык (ru/en)
    
    Returns:
        {
            'invoice_id': 12345,
            'pay_url': 'https://t.me/CryptoBot?start=...',
            'plan': {...}
        }
    """
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    if not plan:
        logger.error(f"Invalid plan_id: {plan_id}")
        return None
    
    # Описание платежа
    if lang == "en":
        description = f"Alpha Entry Bot - {plan['name_en']}"
    else:
        description = f"Alpha Entry Bot - {plan['name']}"
    
    # Payload для идентификации платежа
    payload = f"{user_id}:{plan_id}"
    
    # Создаём инвойс
    invoice = await crypto_api.create_invoice(
        amount=plan["price"],
        currency="USDT",  # Можно добавить выбор валюты
        description=description,
        payload=payload,
        allow_comments=False,
        allow_anonymous=False
    )
    
    if invoice:
        invoice["plan"] = plan
        return invoice
    
    return None

async def check_payment_status(invoice_id: int) -> Optional[str]:
    """
    Проверить статус платежа
    
    Returns:
        'paid' | 'active' | 'expired' | None
    """
    invoice = await crypto_api.get_invoice(invoice_id)
    if invoice:
        return invoice.get("status")
    return None

async def grant_subscription_access(user_id: int, plan_id: str):
    """
    Выдать доступ пользователю после оплаты
    
    Args:
        user_id: ID пользователя
        plan_id: ID тарифного плана
    """
    from database import grant_access, db_pool
    
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    if not plan:
        logger.error(f"Invalid plan_id: {plan_id}")
        return
    
    # Выдаём доступ
    await grant_access(user_id)
    
    # Устанавливаем дату окончания подписки
    expiry_date = datetime.now() + timedelta(days=plan["duration_days"])
    
    conn = await db_pool.acquire()
    try:
        await conn.execute(
            "UPDATE users SET subscription_expiry=?, subscription_plan=? WHERE id=?",
            (int(expiry_date.timestamp()), plan_id, user_id)
        )
        await conn.commit()
        logger.info(f"Granted {plan_id} access to user {user_id} until {expiry_date}")
    finally:
        await db_pool.release(conn)

# ==================== WEBHOOK HANDLER ====================
async def handle_crypto_webhook(signature: str, body: bytes) -> bool:
    """
    Обработать вебхук от Crypto Bot
    
    Args:
        signature: Заголовок Crypto-Pay-API-Signature
        body: Тело запроса
    
    Returns:
        True если обработан успешно
    """
    # Проверяем подпись
    if not crypto_api.verify_webhook(signature, body):
        logger.warning("Invalid webhook signature!")
        return False
    
    try:
        data = json.loads(body.decode())
        update_type = data.get("update_type")
        
        if update_type == "invoice_paid":
            payload_data = data.get("payload")
            invoice_id = payload_data.get("invoice_id")
            status = payload_data.get("status")
            payload = payload_data.get("payload", "")
            
            logger.info(f"Invoice {invoice_id} paid! Payload: {payload}")
            
            # Парсим payload (user_id:plan_id)
            if ":" in payload:
                user_id_str, plan_id = payload.split(":", 1)
                user_id = int(user_id_str)
                
                # Выдаём доступ
                await grant_subscription_access(user_id, plan_id)
                
                # Отправляем уведомление пользователю
                from aiogram import Bot
                from config import BOT_TOKEN
                bot = Bot.get_current()
                
                plan = SUBSCRIPTION_PLANS.get(plan_id)
                text = f"✅ <b>Оплата получена!</b>\n\n"
                text += f"Подписка: {plan['name']}\n"
                text += f"Сумма: ${plan['price']}\n\n"
                text += f"Доступ активирован на {plan['duration_days']} дней!\n\n"
                text += f"Используй /start чтобы начать получать сигналы."
                
                try:
                    await bot.send_message(user_id, text)
                except:
                    pass
                
                return True
                
    except Exception as e:
        logger.error(f"Webhook handling error: {e}")
    
    return False

# ==================== РАСЧЁТ СКИДОК ====================
def calculate_discount(plan_id: str) -> Dict:
    """
    Рассчитать детали скидки
    
    Returns:
        {
            'original_price': 60.00,
            'discount_percent': 17,
            'discount_amount': 10.00,
            'final_price': 50.00
        }
    """
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    if not plan or plan_id == "1m":
        return {}
    
    # Базовая цена = $20/месяц
    base_monthly_price = 20.00
    months = plan["duration_days"] / 30
    original_price = base_monthly_price * months
    final_price = plan["price"]
    discount_amount = original_price - final_price
    discount_percent = (discount_amount / original_price) * 100
    
    return {
        "original_price": original_price,
        "discount_percent": round(discount_percent),
        "discount_amount": round(discount_amount, 2),
        "final_price": final_price,
        "months": int(months)
    }
