"""
database.py - Работа с базой данных
"""
import time
import asyncio
import logging
from typing import List
from datetime import datetime
import aiosqlite

from config import DB_PATH

logger = logging.getLogger(__name__)

# ==================== SQL SCHEMA ====================
INIT_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=10000;
PRAGMA temp_store=MEMORY;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    invited_by INTEGER,
    balance REAL DEFAULT 0,
    paid INTEGER DEFAULT 0,
    language TEXT DEFAULT 'ru',
    created_ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_pairs (
    user_id INTEGER NOT NULL,
    pair TEXT NOT NULL,
    PRIMARY KEY (user_id, pair)
);

CREATE TABLE IF NOT EXISTS signals_sent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    pair TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    score INTEGER NOT NULL,
    sent_ts INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signals_pair_ts ON signals_sent(pair, sent_ts);
CREATE INDEX IF NOT EXISTS idx_user_pairs_user ON user_pairs(user_id);
CREATE INDEX IF NOT EXISTS idx_users_paid ON users(paid);
"""

# ==================== DATABASE POOL ====================
class DBPool:
    """Пул соединений к БД"""
    def __init__(self, path: str, pool_size: int = 5):
        self.path = path
        self.pool_size = pool_size
        self._pool: List[aiosqlite.Connection] = []
        self._available = asyncio.Queue()
        self._initialized = False
    
    async def init(self):
        if self._initialized:
            return
        
        for _ in range(self.pool_size):
            conn = await aiosqlite.connect(self.path)
            conn.row_factory = aiosqlite.Row
            self._pool.append(conn)
            await self._available.put(conn)
        
        conn = await self.acquire()
        try:
            await conn.executescript(INIT_SQL)
            await conn.commit()
        finally:
            await self.release(conn)
        
        self._initialized = True
        logger.info(f"Database pool initialized with {self.pool_size} connections")
    
    async def acquire(self) -> aiosqlite.Connection:
        return await self._available.get()
    
    async def release(self, conn: aiosqlite.Connection):
        await self._available.put(conn)
    
    async def close(self):
        for conn in self._pool:
            await conn.close()

# Глобальный пул
db_pool = DBPool(DB_PATH, pool_size=5)

# ==================== USER FUNCTIONS ====================
async def get_user_lang(uid: int) -> str:
    """Получить язык пользователя"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT language FROM users WHERE id=?", (uid,))
        row = await cursor.fetchone()
        return row["language"] if row and row["language"] else "ru"
    finally:
        await db_pool.release(conn)

async def set_user_lang(uid: int, lang: str):
    """Установить язык пользователя"""
    conn = await db_pool.acquire()
    try:
        await conn.execute("UPDATE users SET language=? WHERE id=?", (lang, uid))
        await conn.commit()
    finally:
        await db_pool.release(conn)

async def is_paid(uid: int) -> bool:
    """Проверить оплачен ли доступ"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT paid FROM users WHERE id=?", (uid,))
        row = await cursor.fetchone()
        return bool(row and row["paid"])
    finally:
        await db_pool.release(conn)

async def get_user_balance(uid: int) -> float:
    """Получить баланс пользователя"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT balance FROM users WHERE id=?", (uid,))
        row = await cursor.fetchone()
        return row["balance"] if row else 0.0
    finally:
        await db_pool.release(conn)

async def get_user_refs_count(uid: int) -> int:
    """Получить количество рефералов"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT COUNT(*) as cnt FROM users WHERE invited_by=? AND paid=1",
            (uid,)
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0
    finally:
        await db_pool.release(conn)

# ==================== PAIRS FUNCTIONS ====================
async def get_user_pairs(uid: int) -> List[str]:
    """Получить пары пользователя"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT pair FROM user_pairs WHERE user_id=?", (uid,))
        rows = await cursor.fetchall()
        return [r["pair"] for r in rows]
    finally:
        await db_pool.release(conn)

async def add_user_pair(uid: int, pair: str):
    """Добавить пару пользователю"""
    conn = await db_pool.acquire()
    try:
        await conn.execute("INSERT OR IGNORE INTO user_pairs(user_id, pair) VALUES(?,?)", (uid, pair.upper()))
        await conn.commit()
    finally:
        await db_pool.release(conn)

async def remove_user_pair(uid: int, pair: str):
    """Удалить пару у пользователя"""
    conn = await db_pool.acquire()
    try:
        await conn.execute("DELETE FROM user_pairs WHERE user_id=? AND pair=?", (uid, pair.upper()))
        await conn.commit()
    finally:
        await db_pool.release(conn)

async def clear_user_pairs(uid: int):
    """Очистить все пары пользователя"""
    conn = await db_pool.acquire()
    try:
        await conn.execute("DELETE FROM user_pairs WHERE user_id=?", (uid,))
        await conn.commit()
    finally:
        await db_pool.release(conn)

async def get_all_tracked_pairs() -> List[str]:
    """Получить все отслеживаемые пары"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT DISTINCT pair FROM user_pairs")
        rows = await cursor.fetchall()
        return [r["pair"] for r in rows]
    finally:
        await db_pool.release(conn)

async def get_pairs_with_users():
    """Получить пары с пользователями (для рассылки сигналов)"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT up.user_id, up.pair FROM user_pairs up "
            "JOIN users u ON up.user_id = u.id WHERE u.paid = 1"
        )
        rows = await cursor.fetchall()
        return rows
    finally:
        await db_pool.release(conn)

# ==================== SIGNALS FUNCTIONS ====================
async def count_signals_today(pair: str) -> int:
    """Подсчитать сигналы за сегодня"""
    conn = await db_pool.acquire()
    try:
        today_start = int(datetime.now().replace(hour=0, minute=0, second=0).timestamp())
        cursor = await conn.execute(
            "SELECT COUNT(*) as cnt FROM signals_sent WHERE pair=? AND sent_ts >= ?",
            (pair, today_start)
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0
    finally:
        await db_pool.release(conn)

async def log_signal(uid: int, pair: str, side: str, price: float, score: int):
    """Записать отправленный сигнал"""
    conn = await db_pool.acquire()
    try:
        await conn.execute(
            "INSERT INTO signals_sent(user_id, pair, side, price, score, sent_ts) VALUES(?,?,?,?,?,?)",
            (uid, pair, side, price, score, int(time.time()))
        )
        await conn.commit()
    finally:
        await db_pool.release(conn)

# ==================== ADMIN FUNCTIONS ====================
async def get_users_count() -> int:
    """Получить общее количество пользователей"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM users")
        row = await cursor.fetchone()
        return row["cnt"] if row else 0
    finally:
        await db_pool.release(conn)

async def get_paid_users_count() -> int:
    """Получить количество оплативших"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM users WHERE paid=1")
        row = await cursor.fetchone()
        return row["cnt"] if row else 0
    finally:
        await db_pool.release(conn)

async def get_active_users_count() -> int:
    """Получить количество активных (с парами)"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM user_pairs")
        row = await cursor.fetchone()
        return row["cnt"] if row else 0
    finally:
        await db_pool.release(conn)

async def get_all_user_ids() -> List[int]:
    """Получить ID всех пользователей"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT id FROM users")
        rows = await cursor.fetchall()
        return [r["id"] for r in rows]
    finally:
        await db_pool.release(conn)

async def grant_access(uid: int):
    """Выдать доступ пользователю"""
    conn = await db_pool.acquire()
    try:
        await conn.execute("INSERT OR IGNORE INTO users(id, created_ts) VALUES(?,?)", (uid, int(time.time())))
        await conn.execute("UPDATE users SET paid=1 WHERE id=?", (uid,))
        await conn.commit()
    finally:
        await db_pool.release(conn)

async def add_balance(uid: int, amount: float):
    """Добавить баланс пользователю"""
    conn = await db_pool.acquire()
    try:
        await conn.execute("INSERT OR IGNORE INTO users(id, created_ts) VALUES(?,?)", (uid, int(time.time())))
        await conn.execute("UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE id=?", (amount, uid))
        await conn.commit()
    finally:
        await db_pool.release(conn)

# ==================== INIT ====================
async def init_db():
    """Инициализация базы данных"""
    await db_pool.init()