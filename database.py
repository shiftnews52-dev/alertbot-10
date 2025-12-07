"""
database.py - База данных с поддержкой платных подписок
ИСПРАВЛЕНО: get_pairs_with_users, log_signal, добавлена таблица signal_logs
"""
import aiosqlite
import logging
from datetime import datetime

from config import DB_PATH

logger = logging.getLogger(__name__)

# SQL схема - ИСПРАВЛЕНО: добавлена таблица signal_logs
INIT_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    invited_by INTEGER,
    balance REAL DEFAULT 0,
    paid INTEGER DEFAULT 0,
    language TEXT DEFAULT 'ru',
    min_score INTEGER DEFAULT 70,
    subscription_expiry INTEGER,
    subscription_plan TEXT,
    created_ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_pairs (
    user_id INTEGER,
    pair TEXT,
    enabled INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, pair)
);

CREATE TABLE IF NOT EXISTS active_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    pair TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    tp1_price REAL NOT NULL,
    tp2_price REAL NOT NULL,
    tp3_price REAL NOT NULL,
    sl_price REAL NOT NULL,
    score INTEGER NOT NULL,
    reasons TEXT,
    tp1_hit INTEGER DEFAULT 0,
    tp2_hit INTEGER DEFAULT 0,
    tp3_hit INTEGER DEFAULT 0,
    sl_hit INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    created_ts INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS closed_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    pair TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    pnl_percent REAL NOT NULL,
    result TEXT NOT NULL,
    created_ts INTEGER NOT NULL,
    closed_ts INTEGER NOT NULL,
    duration_hours REAL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- НОВАЯ ТАБЛИЦА: Логи отправленных сигналов
CREATE TABLE IF NOT EXISTS signal_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    tp1 REAL,
    tp2 REAL,
    tp3 REAL,
    sl REAL,
    score INTEGER,
    created_ts INTEGER NOT NULL
);

-- Индекс для подсчёта сигналов за день
CREATE INDEX IF NOT EXISTS idx_signal_logs_pair_ts ON signal_logs(pair, created_ts);
"""

# Пул соединений
db_pool = None

class DatabasePool:
    """Простой пул соединений для SQLite"""
    def __init__(self, db_path, pool_size=5):
        self.db_path = db_path
        self.pool = []
        self.pool_size = pool_size
    
    async def init(self):
        """Инициализация пула"""
        for _ in range(self.pool_size):
            conn = await aiosqlite.connect(self.db_path)
            conn.row_factory = aiosqlite.Row
            self.pool.append(conn)
        logger.info(f"Database pool initialized with {self.pool_size} connections")
    
    async def acquire(self):
        """Получить соединение из пула"""
        if self.pool:
            return self.pool.pop(0)
        # Если пул пуст, создаём новое соединение
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        return conn
    
    async def release(self, conn):
        """Вернуть соединение в пул"""
        if len(self.pool) < self.pool_size:
            self.pool.append(conn)
        else:
            await conn.close()
    
    async def close_all(self):
        """Закрыть все соединения"""
        for conn in self.pool:
            await conn.close()
        self.pool.clear()

async def init_db():
    """Инициализация базы данных"""
    global db_pool
    
    # Создаём пул
    db_pool = DatabasePool(DB_PATH, pool_size=5)
    await db_pool.init()
    
    # Создаём таблицы
    conn = await db_pool.acquire()
    try:
        await conn.executescript(INIT_SQL)
        await conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise
    finally:
        await db_pool.release(conn)

async def add_user(user_id: int, lang: str = "ru", invited_by: int = None):
    """Добавить нового пользователя"""
    conn = await db_pool.acquire()
    try:
        created_ts = int(datetime.now().timestamp())
        await conn.execute(
            "INSERT OR IGNORE INTO users (id, language, invited_by, created_ts) VALUES (?, ?, ?, ?)",
            (user_id, lang, invited_by, created_ts)
        )
        await conn.commit()
    finally:
        await db_pool.release(conn)

async def user_exists(user_id: int) -> bool:
    """Проверить существует ли пользователь"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT id FROM users WHERE id=?", (user_id,))
        row = await cursor.fetchone()
        return row is not None
    finally:
        await db_pool.release(conn)

async def get_user_lang(user_id: int) -> str:
    """Получить язык пользователя"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT language FROM users WHERE id=?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else "ru"
    finally:
        await db_pool.release(conn)

async def set_user_lang(user_id: int, lang: str):
    """Установить язык пользователя"""
    conn = await db_pool.acquire()
    try:
        await conn.execute("UPDATE users SET language=? WHERE id=?", (lang, user_id))
        await conn.commit()
    finally:
        await db_pool.release(conn)

async def is_paid(user_id: int) -> bool:
    """Проверить оплачен ли доступ"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT paid, subscription_expiry FROM users WHERE id=?", 
            (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return False
        
        # Проверяем флаг paid
        if row[0] == 1:
            # Если есть срок действия подписки
            if row[1]:
                # Проверяем не истёк ли срок
                if row[1] > int(datetime.now().timestamp()):
                    return True
                else:
                    # Срок истёк - снимаем флаг
                    await conn.execute("UPDATE users SET paid=0 WHERE id=?", (user_id,))
                    await conn.commit()
                    return False
            return True
        return False
    finally:
        await db_pool.release(conn)

async def grant_access(user_id: int, days: int = 30):
    """Выдать доступ пользователю на N дней"""
    from datetime import datetime, timedelta
    
    conn = await db_pool.acquire()
    try:
        # Вычисляем дату окончания подписки
        expiry_ts = int((datetime.now() + timedelta(days=days)).timestamp())
        
        await conn.execute(
            "UPDATE users SET paid=1, subscription_expiry=? WHERE id=?", 
            (expiry_ts, user_id)
        )
        await conn.commit()
        logger.info(f"Access granted to user {user_id} for {days} days (until {datetime.fromtimestamp(expiry_ts)})")
    finally:
        await db_pool.release(conn)

async def revoke_access(user_id: int):
    """Отозвать доступ"""
    conn = await db_pool.acquire()
    try:
        await conn.execute("UPDATE users SET paid=0 WHERE id=?", (user_id,))
        await conn.commit()
        logger.info(f"Access revoked from user {user_id}")
    finally:
        await db_pool.release(conn)

async def get_subscription_info(user_id: int) -> dict:
    """Получить информацию о подписке"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT subscription_expiry, subscription_plan FROM users WHERE id=?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row and row[0]:
            expiry_ts = row[0]
            expiry_date = datetime.fromtimestamp(expiry_ts)
            days_left = (expiry_date - datetime.now()).days
            
            return {
                "expiry_date": expiry_date,
                "expiry_ts": expiry_ts,
                "plan": row[1],
                "days_left": max(0, days_left),
                "is_active": expiry_ts > int(datetime.now().timestamp())
            }
        return None
    finally:
        await db_pool.release(conn)

async def add_balance(user_id: int, amount: float):
    """Добавить баланс"""
    conn = await db_pool.acquire()
    try:
        await conn.execute(
            "UPDATE users SET balance = balance + ? WHERE id=?",
            (amount, user_id)
        )
        await conn.commit()
    finally:
        await db_pool.release(conn)

async def get_balance(user_id: int) -> float:
    """Получить баланс"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT balance FROM users WHERE id=?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0.0
    finally:
        await db_pool.release(conn)

async def get_user_pairs(user_id: int) -> list:
    """Получить пары пользователя"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT pair FROM user_pairs WHERE user_id=? AND enabled=1",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]
    finally:
        await db_pool.release(conn)

async def add_user_pair(user_id: int, pair: str):
    """Добавить пару"""
    conn = await db_pool.acquire()
    try:
        await conn.execute(
            "INSERT OR REPLACE INTO user_pairs (user_id, pair, enabled) VALUES (?, ?, 1)",
            (user_id, pair)
        )
        await conn.commit()
    finally:
        await db_pool.release(conn)

async def remove_user_pair(user_id: int, pair: str):
    """Удалить пару"""
    conn = await db_pool.acquire()
    try:
        await conn.execute(
            "DELETE FROM user_pairs WHERE user_id=? AND pair=?",
            (user_id, pair)
        )
        await conn.commit()
    finally:
        await db_pool.release(conn)

async def get_all_paid_users() -> list:
    """Получить всех оплативших пользователей"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT id FROM users WHERE paid=1 AND (subscription_expiry IS NULL OR subscription_expiry > ?)",
            (int(datetime.now().timestamp()),)
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]
    finally:
        await db_pool.release(conn)

async def get_min_score(user_id: int) -> int:
    """Получить минимальный score"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT min_score FROM users WHERE id=?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 70
    finally:
        await db_pool.release(conn)

async def set_min_score(user_id: int, score: int):
    """Установить минимальный score"""
    conn = await db_pool.acquire()
    try:
        await conn.execute("UPDATE users SET min_score=? WHERE id=?", (score, user_id))
        await conn.commit()
    finally:
        await db_pool.release(conn)

async def get_total_users() -> int:
    """Получить общее количество пользователей"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        return row[0] if row else 0
    finally:
        await db_pool.release(conn)

async def get_paid_users_count() -> int:
    """Получить количество оплативших"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM users WHERE paid=1 AND (subscription_expiry IS NULL OR subscription_expiry > ?)",
            (int(datetime.now().timestamp()),)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0
    finally:
        await db_pool.release(conn)

async def get_all_user_ids() -> list:
    """Получить ID всех пользователей"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT id FROM users")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]
    finally:
        await db_pool.release(conn)

async def close_db():
    """Закрыть соединение с базой данных"""
    global db_pool
    if db_pool:
        await db_pool.close_all()
        logger.info("✅ Database connection closed")

async def get_all_tracked_pairs() -> list:
    """Получить все отслеживаемые пары (для Системы 2)"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT DISTINCT pair FROM user_pairs WHERE enabled=1"
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows] if rows else []
    finally:
        await db_pool.release(conn)


# ==================== ИСПРАВЛЕНИЕ: Новая сигнатура ====================
async def get_pairs_with_users() -> list:
    """
    Получить все пары с пользователями (для Системы 2)
    ИСПРАВЛЕНО: Теперь возвращает список словарей с парой и user_id
    
    Returns:
        [{"pair": "BTCUSDT", "user_id": 123}, ...]
    """
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            """SELECT DISTINCT up.pair, up.user_id 
               FROM user_pairs up
               JOIN users u ON up.user_id = u.id
               WHERE up.enabled=1 AND u.paid=1
               AND (u.subscription_expiry IS NULL OR u.subscription_expiry > ?)""",
            (int(datetime.now().timestamp()),)
        )
        rows = await cursor.fetchall()
        return [{"pair": row[0], "user_id": row[1]} for row in rows] if rows else []
    finally:
        await db_pool.release(conn)


async def get_users_for_pair(pair: str) -> list:
    """
    Получить список пользователей отслеживающих конкретную пару
    
    Args:
        pair: Торговая пара (например BTCUSDT)
    
    Returns:
        [user_id, user_id, ...]
    """
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            """SELECT up.user_id FROM user_pairs up
               JOIN users u ON up.user_id = u.id
               WHERE up.pair=? AND up.enabled=1 AND u.paid=1
               AND (u.subscription_expiry IS NULL OR u.subscription_expiry > ?)""",
            (pair, int(datetime.now().timestamp()))
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows] if rows else []
    finally:
        await db_pool.release(conn)


# ==================== ИСПРАВЛЕНИЕ: Реализована функция ====================
async def count_signals_today(pair: str) -> int:
    """
    Подсчитать сколько сигналов отправлено сегодня для пары
    ИСПРАВЛЕНО: Теперь реально считает из таблицы signal_logs
    """
    conn = await db_pool.acquire()
    try:
        # Начало сегодняшнего дня
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = int(today_start.timestamp())
        
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM signal_logs WHERE pair=? AND created_ts >= ?",
            (pair, today_ts)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0
    finally:
        await db_pool.release(conn)


# ==================== ИСПРАВЛЕНИЕ: Реализована функция ====================
async def log_signal(pair: str, side: str, entry_price: float, score: int = 0):
    """
    Логировать отправленный сигнал
    ИСПРАВЛЕНО: Теперь реально сохраняет в БД
    
    Args:
        pair: Торговая пара
        side: LONG или SHORT
        entry_price: Цена входа
        score: Confidence score
    """
    conn = await db_pool.acquire()
    try:
        await conn.execute(
            """INSERT INTO signal_logs (pair, side, entry_price, score, created_ts)
               VALUES (?, ?, ?, ?, ?)""",
            (pair, side, entry_price, score, int(datetime.now().timestamp()))
        )
        await conn.commit()
        logger.debug(f"Signal logged: {pair} {side} @ {entry_price}")
    except Exception as e:
        logger.error(f"Error logging signal: {e}")
    finally:
        await db_pool.release(conn)


async def get_all_users() -> list:
    """
    Получить список всех user_id для рассылки
    
    Returns:
        [user_id, user_id, ...]
    """
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT id FROM users")
        rows = await cursor.fetchall()
        return [row[0] for row in rows] if rows else []
    finally:
        await db_pool.release(conn)


# ==================== БЭКАП СИСТЕМЫ ====================
import json

async def export_users_backup() -> dict:
    """
    Экспорт всех пользователей для бэкапа
    
    Returns:
        {
            "exported_at": "2024-12-06T12:00:00",
            "total_users": 150,
            "premium_users": 25,
            "users": [
                {
                    "id": 123456789,
                    "paid": 1,
                    "language": "ru",
                    "subscription_expiry": 1735689600,
                    "subscription_plan": "3m",
                    "balance": 0,
                    "invited_by": null,
                    "created_ts": 1701864000,
                    "pairs": ["BTCUSDT", "ETHUSDT"]
                },
                ...
            ]
        }
    """
    conn = await db_pool.acquire()
    try:
        # Получаем всех пользователей
        cursor = await conn.execute("""
            SELECT id, invited_by, balance, paid, language, 
                   subscription_expiry, subscription_plan, created_ts
            FROM users
        """)
        users_rows = await cursor.fetchall()
        
        users_data = []
        premium_count = 0
        
        for row in users_rows:
            user_id = row[0]
            
            # Получаем пары пользователя
            pairs_cursor = await conn.execute(
                "SELECT pair FROM user_pairs WHERE user_id = ? AND enabled = 1",
                (user_id,)
            )
            pairs_rows = await pairs_cursor.fetchall()
            pairs = [p[0] for p in pairs_rows] if pairs_rows else []
            
            user_data = {
                "id": user_id,
                "invited_by": row[1],
                "balance": row[2],
                "paid": row[3],
                "language": row[4],
                "subscription_expiry": row[5],
                "subscription_plan": row[6],
                "created_ts": row[7],
                "pairs": pairs
            }
            users_data.append(user_data)
            
            if row[3] == 1:  # paid
                premium_count += 1
        
        backup = {
            "exported_at": datetime.now().isoformat(),
            "total_users": len(users_data),
            "premium_users": premium_count,
            "users": users_data
        }
        
        logger.info(f"Backup exported: {len(users_data)} users, {premium_count} premium")
        return backup
        
    finally:
        await db_pool.release(conn)


async def import_users_backup(backup_data: dict) -> dict:
    """
    Импорт пользователей из бэкапа
    
    Args:
        backup_data: Данные бэкапа
        
    Returns:
        {"imported": 150, "skipped": 5, "errors": 0}
    """
    conn = await db_pool.acquire()
    try:
        imported = 0
        skipped = 0
        errors = 0
        
        users = backup_data.get("users", [])
        
        for user in users:
            try:
                user_id = user["id"]
                
                # Проверяем существует ли пользователь
                cursor = await conn.execute(
                    "SELECT id FROM users WHERE id = ?", (user_id,)
                )
                exists = await cursor.fetchone()
                
                if exists:
                    # Обновляем существующего (сохраняем подписку)
                    await conn.execute("""
                        UPDATE users SET 
                            paid = ?,
                            subscription_expiry = ?,
                            subscription_plan = ?,
                            balance = ?
                        WHERE id = ?
                    """, (
                        user.get("paid", 0),
                        user.get("subscription_expiry"),
                        user.get("subscription_plan"),
                        user.get("balance", 0),
                        user_id
                    ))
                    skipped += 1
                else:
                    # Создаём нового
                    await conn.execute("""
                        INSERT INTO users (id, invited_by, balance, paid, language, 
                                          subscription_expiry, subscription_plan, created_ts)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_id,
                        user.get("invited_by"),
                        user.get("balance", 0),
                        user.get("paid", 0),
                        user.get("language", "ru"),
                        user.get("subscription_expiry"),
                        user.get("subscription_plan"),
                        user.get("created_ts", int(datetime.now().timestamp()))
                    ))
                    imported += 1
                
                # Восстанавливаем пары
                pairs = user.get("pairs", [])
                for pair in pairs:
                    await conn.execute("""
                        INSERT OR REPLACE INTO user_pairs (user_id, pair, enabled)
                        VALUES (?, ?, 1)
                    """, (user_id, pair))
                
            except Exception as e:
                logger.error(f"Error importing user {user.get('id')}: {e}")
                errors += 1
        
        await conn.commit()
        
        result = {"imported": imported, "updated": skipped, "errors": errors}
        logger.info(f"Backup imported: {result}")
        return result
        
    finally:
        await db_pool.release(conn)


async def get_backup_stats() -> dict:
    """Статистика для бэкапа"""
    conn = await db_pool.acquire()
    try:
        # Всего пользователей
        cursor = await conn.execute("SELECT COUNT(*) FROM users")
        total = (await cursor.fetchone())[0]
        
        # Премиум пользователей
        cursor = await conn.execute("SELECT COUNT(*) FROM users WHERE paid = 1")
        premium = (await cursor.fetchone())[0]
        
        # С активной подпиской
        now_ts = int(datetime.now().timestamp())
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM users WHERE subscription_expiry > ?", (now_ts,)
        )
        active_sub = (await cursor.fetchone())[0]
        
        return {
            "total_users": total,
            "premium_users": premium,
            "active_subscriptions": active_sub
        }
    finally:
        await db_pool.release(conn)


# ==================== РЕФЕРАЛЬНАЯ СИСТЕМА ====================

async def set_referrer(user_id: int, referrer_id: int) -> bool:
    """
    Установить реферера для пользователя
    
    Args:
        user_id: ID нового пользователя
        referrer_id: ID того, кто пригласил
        
    Returns:
        True если успешно
    """
    # Нельзя быть своим рефером
    if user_id == referrer_id:
        return False
    
    conn = await db_pool.acquire()
    try:
        # Проверяем что реферер существует
        cursor = await conn.execute("SELECT id FROM users WHERE id=?", (referrer_id,))
        if not await cursor.fetchone():
            return False
        
        # Устанавливаем реферера
        await conn.execute(
            "UPDATE users SET invited_by=? WHERE id=? AND invited_by IS NULL",
            (referrer_id, user_id)
        )
        await conn.commit()
        logger.info(f"Referrer set: user {user_id} invited by {referrer_id}")
        return True
    except Exception as e:
        logger.error(f"Error setting referrer: {e}")
        return False
    finally:
        await db_pool.release(conn)


async def get_referrer(user_id: int) -> int:
    """Получить ID реферера пользователя"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT invited_by FROM users WHERE id=?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] else None
    finally:
        await db_pool.release(conn)


async def get_referral_count(user_id: int) -> int:
    """Получить количество рефералов пользователя"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM users WHERE invited_by=?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0
    finally:
        await db_pool.release(conn)


async def get_referral_earnings(user_id: int) -> float:
    """Получить реферальный заработок пользователя"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT balance FROM users WHERE id=?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] else 0.0
    finally:
        await db_pool.release(conn)


async def add_referral_bonus(referrer_id: int, amount: float, from_user_id: int) -> bool:
    """
    Начислить реферальный бонус
    
    Args:
        referrer_id: ID реферера (кому начисляем)
        amount: Сумма бонуса
        from_user_id: ID пользователя который оплатил
        
    Returns:
        True если успешно
    """
    conn = await db_pool.acquire()
    try:
        # Начисляем бонус
        await conn.execute(
            "UPDATE users SET balance = balance + ? WHERE id=?",
            (amount, referrer_id)
        )
        await conn.commit()
        logger.info(f"Referral bonus: {referrer_id} got ${amount:.2f} from user {from_user_id}")
        return True
    except Exception as e:
        logger.error(f"Error adding referral bonus: {e}")
        return False
    finally:
        await db_pool.release(conn)


async def get_referral_stats(user_id: int) -> dict:
    """
    Получить полную статистику рефералов
    
    Returns:
        {
            "total_referrals": 10,
            "paid_referrals": 3,
            "earnings": 45.00
        }
    """
    conn = await db_pool.acquire()
    try:
        # Всего рефералов
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM users WHERE invited_by=?", (user_id,)
        )
        total = (await cursor.fetchone())[0]
        
        # Оплативших рефералов
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM users WHERE invited_by=? AND paid=1", (user_id,)
        )
        paid = (await cursor.fetchone())[0]
        
        # Заработок
        cursor = await conn.execute(
            "SELECT balance FROM users WHERE id=?", (user_id,)
        )
        row = await cursor.fetchone()
        earnings = row[0] if row and row[0] else 0.0
        
        return {
            "total_referrals": total,
            "paid_referrals": paid,
            "earnings": earnings
        }
    finally:
        await db_pool.release(conn)


async def get_all_referral_stats() -> list:
    """
    Получить статистику ВСЕХ рефералов для админа
    
    Returns:
        [
            {"user_id": 123, "referrals": 5, "paid_referrals": 2, "earnings": 30.0, "pending": 30.0},
            ...
        ]
    """
    conn = await db_pool.acquire()
    try:
        # Находим всех у кого есть рефералы или заработок
        cursor = await conn.execute("""
            SELECT u.id, u.balance,
                   (SELECT COUNT(*) FROM users r WHERE r.invited_by = u.id) as total_refs,
                   (SELECT COUNT(*) FROM users r WHERE r.invited_by = u.id AND r.paid = 1) as paid_refs
            FROM users u
            WHERE u.balance > 0 OR EXISTS (SELECT 1 FROM users r WHERE r.invited_by = u.id)
            ORDER BY u.balance DESC
        """)
        rows = await cursor.fetchall()
        
        result = []
        for row in rows:
            result.append({
                "user_id": row[0],
                "earnings": row[1] or 0,
                "total_referrals": row[2],
                "paid_referrals": row[3]
            })
        
        return result
    finally:
        await db_pool.release(conn)


async def reset_referral_balance(user_id: int) -> float:
    """
    Сбросить баланс после выплаты (вернуть сумму которая была)
    """
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT balance FROM users WHERE id=?", (user_id,)
        )
        row = await cursor.fetchone()
        old_balance = row[0] if row and row[0] else 0.0
        
        await conn.execute(
            "UPDATE users SET balance = 0 WHERE id=?", (user_id,)
        )
        await conn.commit()
        
        logger.info(f"Referral balance reset: user {user_id}, was ${old_balance:.2f}")
        return old_balance
    finally:
        await db_pool.release(conn)
