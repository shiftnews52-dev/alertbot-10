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

async def grant_access(user_id: int):
    """Выдать доступ пользователю"""
    conn = await db_pool.acquire()
    try:
        await conn.execute("UPDATE users SET paid=1 WHERE id=?", (user_id,))
        await conn.commit()
        logger.info(f"Access granted to user {user_id}")
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
