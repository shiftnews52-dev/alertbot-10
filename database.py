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
    username TEXT,
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
        
        # Таблица менеджеров
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS managers (
                code TEXT PRIMARY KEY,
                name TEXT,
                telegram_id INTEGER,
                balance REAL DEFAULT 0,
                partners_count INTEGER DEFAULT 0,
                conversions INTEGER DEFAULT 0,
                created_ts INTEGER
            )
        """)
        
        # МИГРАЦИЯ: Удаляем старые таблицы и создаём новые с правильной структурой
        # active_signals - для tracking
        await conn.execute("DROP TABLE IF EXISTS active_signals")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS active_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT NOT NULL,
                side TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                entry_price REAL NOT NULL,
                entry_min REAL,
                entry_max REAL,
                tp1 REAL,
                tp2 REAL,
                tp3 REAL,
                stop_loss REAL,
                entry_hit INTEGER DEFAULT 0,
                tp1_hit INTEGER DEFAULT 0,
                tp2_hit INTEGER DEFAULT 0,
                tp3_hit INTEGER DEFAULT 0,
                sl_hit INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_ts INTEGER,
                closed_ts INTEGER,
                profit_percent REAL
            )
        """)
        
        # signal_history - для антидублирования
        await conn.execute("DROP TABLE IF EXISTS signal_history")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT NOT NULL,
                side TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                entry_price REAL NOT NULL,
                confidence REAL,
                created_ts INTEGER,
                sent_to_pro INTEGER DEFAULT 0,
                sent_to_free INTEGER DEFAULT 0,
                free_send_ts INTEGER
            )
        """)
        
        # daily_signal_counts - счётчики за день
        await conn.execute("DROP TABLE IF EXISTS daily_signal_counts")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_signal_counts (
                date TEXT PRIMARY KEY,
                rare_count INTEGER DEFAULT 0,
                high_count INTEGER DEFAULT 0,
                medium_count INTEGER DEFAULT 0,
                free_sent INTEGER DEFAULT 0
            )
        """)
        
        logger.info("✅ Signal tracking tables created/migrated")
        
        # Миграция: добавляем колонку username если нет
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
            logger.info("Added username column to users table")
        except:
            pass  # Колонка уже существует
        
        # Миграция: промо-система и реф-система
        migrations = [
            ("was_subscriber", "INTEGER DEFAULT 0"),
            ("last_promo_at", "INTEGER DEFAULT 0"),
            ("last_promo_index", "INTEGER DEFAULT 0"),
            ("reminder_2d_sent", "INTEGER DEFAULT 0"),
            ("role", "TEXT DEFAULT 'user'"),
            ("manager_id", "TEXT"),  # Теперь хранит CODE менеджера, не ID
            ("first_payment_done", "INTEGER DEFAULT 0"),
            ("trial_used", "INTEGER DEFAULT 0"),  # Использовал ли триал
        ]
        
        for col_name, col_type in migrations:
            try:
                await conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                logger.info(f"Added {col_name} column to users table")
            except:
                pass
        
        await conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise
    finally:
        await db_pool.release(conn)

async def add_user(user_id: int, lang: str = "ru", invited_by: int = None, username: str = None):
    """Добавить нового пользователя"""
    conn = await db_pool.acquire()
    try:
        created_ts = int(datetime.now().timestamp())
        await conn.execute(
            "INSERT OR IGNORE INTO users (id, language, invited_by, username, created_ts) VALUES (?, ?, ?, ?, ?)",
            (user_id, lang, invited_by, username, created_ts)
        )
        await conn.commit()
    finally:
        await db_pool.release(conn)


async def update_username(user_id: int, username: str):
    """Обновить username пользователя"""
    conn = await db_pool.acquire()
    try:
        await conn.execute(
            "UPDATE users SET username = ? WHERE id = ?",
            (username, user_id)
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
            SELECT id, username, invited_by, balance, paid, language, 
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
                "username": row[1],
                "invited_by": row[2],
                "balance": row[3],
                "paid": row[4],
                "language": row[5],
                "subscription_expiry": row[6],
                "subscription_plan": row[7],
                "created_ts": row[8],
                "pairs": pairs
            }
            users_data.append(user_data)
            
            if row[4] == 1:  # paid
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
                            balance = ?,
                            username = COALESCE(?, username)
                        WHERE id = ?
                    """, (
                        user.get("paid", 0),
                        user.get("subscription_expiry"),
                        user.get("subscription_plan"),
                        user.get("balance", 0),
                        user.get("username"),
                        user_id
                    ))
                    skipped += 1
                else:
                    # Создаём нового
                    await conn.execute("""
                        INSERT INTO users (id, username, invited_by, balance, paid, language, 
                                          subscription_expiry, subscription_plan, created_ts)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_id,
                        user.get("username"),
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
            {"user_id": 123, "username": "user123", "referrals": 5, "paid_referrals": 2, "earnings": 30.0},
            ...
        ]
    """
    conn = await db_pool.acquire()
    try:
        # Находим всех у кого есть рефералы или заработок
        cursor = await conn.execute("""
            SELECT u.id, u.username, u.balance,
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
                "username": row[1],
                "earnings": row[2] or 0,
                "total_referrals": row[3],
                "paid_referrals": row[4]
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


# ==================== ПРОМО-СИСТЕМА ====================

async def get_users_expiring_soon(days_before: int = 2) -> list:
    """
    Получить пользователей у которых подписка истекает через N дней
    И им ещё не отправляли напоминание
    """
    conn = await db_pool.acquire()
    try:
        now_ts = int(datetime.now().timestamp())
        target_ts = now_ts + (days_before * 24 * 3600)
        # Окно: от now до target_ts (т.е. истекает в ближайшие N дней)
        
        cursor = await conn.execute("""
            SELECT id, username, language, subscription_expiry 
            FROM users 
            WHERE paid = 1 
              AND subscription_expiry IS NOT NULL
              AND subscription_expiry > ?
              AND subscription_expiry <= ?
              AND (reminder_2d_sent IS NULL OR reminder_2d_sent = 0)
        """, (now_ts, target_ts))
        
        rows = await cursor.fetchall()
        return [{"user_id": r[0], "username": r[1], "lang": r[2] or "ru", "expiry": r[3]} for r in rows]
    finally:
        await db_pool.release(conn)


async def mark_reminder_sent(user_id: int):
    """Пометить что напоминание отправлено"""
    conn = await db_pool.acquire()
    try:
        await conn.execute(
            "UPDATE users SET reminder_2d_sent = 1 WHERE id = ?", 
            (user_id,)
        )
        await conn.commit()
    finally:
        await db_pool.release(conn)


async def get_expired_subscriptions() -> list:
    """Получить пользователей с только что истёкшей подпиской (для уведомления)"""
    conn = await db_pool.acquire()
    try:
        now_ts = int(datetime.now().timestamp())
        # Истёк в последние 24 часа и ещё paid=1 (не обработан)
        day_ago = now_ts - (24 * 3600)
        
        cursor = await conn.execute("""
            SELECT id, username, language, subscription_expiry 
            FROM users 
            WHERE paid = 1 
              AND subscription_expiry IS NOT NULL
              AND subscription_expiry < ?
              AND subscription_expiry > ?
        """, (now_ts, day_ago))
        
        rows = await cursor.fetchall()
        return [{"user_id": r[0], "username": r[1], "lang": r[2] or "ru", "expiry": r[3]} for r in rows]
    finally:
        await db_pool.release(conn)


async def expire_subscription(user_id: int):
    """
    Истечь подписку: 
    - paid = 0
    - was_subscriber = 1 (для скидки на продление)
    - reminder_2d_sent = 0 (сброс для будущего)
    """
    conn = await db_pool.acquire()
    try:
        await conn.execute("""
            UPDATE users SET 
                paid = 0, 
                was_subscriber = 1,
                reminder_2d_sent = 0
            WHERE id = ?
        """, (user_id,))
        await conn.commit()
        logger.info(f"Subscription expired for user {user_id}")
    finally:
        await db_pool.release(conn)


async def get_users_for_promo(interval_hours: int = 48) -> list:
    """
    Получить неподписанных пользователей для промо
    Которым не отправляли сообщение последние N часов
    """
    conn = await db_pool.acquire()
    try:
        now_ts = int(datetime.now().timestamp())
        min_last_promo = now_ts - (interval_hours * 3600)
        
        cursor = await conn.execute("""
            SELECT id, username, language, last_promo_index
            FROM users 
            WHERE paid = 0
              AND (last_promo_at IS NULL OR last_promo_at < ?)
        """, (min_last_promo,))
        
        rows = await cursor.fetchall()
        return [{
            "user_id": r[0], 
            "username": r[1], 
            "lang": r[2] or "ru",
            "last_index": r[3] or 0
        } for r in rows]
    finally:
        await db_pool.release(conn)


async def update_promo_sent(user_id: int, promo_index: int):
    """Обновить статус отправки промо"""
    conn = await db_pool.acquire()
    try:
        now_ts = int(datetime.now().timestamp())
        await conn.execute("""
            UPDATE users SET 
                last_promo_at = ?,
                last_promo_index = ?
            WHERE id = ?
        """, (now_ts, promo_index, user_id))
        await conn.commit()
    finally:
        await db_pool.release(conn)


async def was_subscriber(user_id: int) -> bool:
    """Проверить был ли пользователь когда-то подписчиком (для скидки)"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT was_subscriber FROM users WHERE id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        return bool(row and row[0])
    finally:
        await db_pool.release(conn)


async def get_all_expired_to_cleanup() -> list:
    """Получить всех с истёкшей подпиской для фоновой очистки"""
    conn = await db_pool.acquire()
    try:
        now_ts = int(datetime.now().timestamp())
        
        cursor = await conn.execute("""
            SELECT id FROM users 
            WHERE paid = 1 
              AND subscription_expiry IS NOT NULL
              AND subscription_expiry < ?
        """, (now_ts,))
        
        rows = await cursor.fetchall()
        return [r[0] for r in rows]
    finally:
        await db_pool.release(conn)


async def get_paid_users_list() -> list:
    """Получить список всех платных пользователей с username и ID"""
    conn = await db_pool.acquire()
    try:
        now_ts = int(datetime.now().timestamp())
        
        cursor = await conn.execute("""
            SELECT id, username, subscription_expiry 
            FROM users 
            WHERE paid = 1 
              AND (subscription_expiry IS NULL OR subscription_expiry > ?)
            ORDER BY subscription_expiry DESC
        """, (now_ts,))
        
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            days_left = None
            if r[2]:
                days_left = max(0, (r[2] - now_ts) // 86400)
            result.append({
                "user_id": r[0],
                "username": r[1],
                "days_left": days_left
            })
        return result
    finally:
        await db_pool.release(conn)


# ==================== ТРЁХУРОВНЕВАЯ РЕФЕРАЛЬНАЯ СИСТЕМА ====================
# Manager → Partner → User
# При первой оплате: Partner +$10, Manager +$3

# Таблица менеджеров (создаётся при init_db)
MANAGERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS managers (
    code TEXT PRIMARY KEY,
    name TEXT,
    telegram_id INTEGER,
    balance REAL DEFAULT 0,
    partners_count INTEGER DEFAULT 0,
    conversions INTEGER DEFAULT 0,
    created_ts INTEGER
);
"""


async def init_managers_table():
    """Создать таблицу менеджеров если не существует"""
    conn = await db_pool.acquire()
    try:
        await conn.execute(MANAGERS_TABLE_SQL)
        await conn.commit()
        logger.info("Managers table initialized")
    finally:
        await db_pool.release(conn)


async def create_manager(code: str, name: str = None, telegram_id: int = None) -> bool:
    """
    Создать нового менеджера по коду
    
    Args:
        code: Уникальный код (например: 'john', 'channel1', 'promo2024')
        name: Имя/описание менеджера
        telegram_id: Telegram ID (опционально, можно привязать позже)
    """
    conn = await db_pool.acquire()
    try:
        # Проверяем что код не занят
        cursor = await conn.execute("SELECT code FROM managers WHERE code = ?", (code,))
        if await cursor.fetchone():
            return False
        
        created_ts = int(datetime.now().timestamp())
        await conn.execute(
            "INSERT INTO managers (code, name, telegram_id, created_ts) VALUES (?, ?, ?, ?)",
            (code, name, telegram_id, created_ts)
        )
        await conn.commit()
        logger.info(f"Manager created: code={code}, name={name}, tg_id={telegram_id}")
        return True
    finally:
        await db_pool.release(conn)


async def get_manager_by_code(code: str) -> dict:
    """Получить менеджера по коду"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT code, name, telegram_id, balance, partners_count, conversions FROM managers WHERE code = ?",
            (code,)
        )
        row = await cursor.fetchone()
        if row:
            return {
                "code": row[0],
                "name": row[1],
                "telegram_id": row[2],
                "balance": row[3] or 0,
                "partners_count": row[4] or 0,
                "conversions": row[5] or 0
            }
        return None
    finally:
        await db_pool.release(conn)


async def link_manager_telegram(code: str, telegram_id: int) -> bool:
    """Привязать Telegram ID к менеджеру"""
    conn = await db_pool.acquire()
    try:
        await conn.execute(
            "UPDATE managers SET telegram_id = ? WHERE code = ?",
            (telegram_id, code)
        )
        await conn.commit()
        return True
    finally:
        await db_pool.release(conn)


async def add_manager_bonus(code: str, amount: float):
    """Начислить бонус менеджеру"""
    conn = await db_pool.acquire()
    try:
        await conn.execute(
            "UPDATE managers SET balance = balance + ?, conversions = conversions + 1 WHERE code = ?",
            (amount, code)
        )
        await conn.commit()
        logger.info(f"Manager {code} got ${amount:.2f} bonus")
    finally:
        await db_pool.release(conn)


async def increment_manager_partners(code: str):
    """Увеличить счётчик партнёров менеджера"""
    conn = await db_pool.acquire()
    try:
        await conn.execute(
            "UPDATE managers SET partners_count = partners_count + 1 WHERE code = ?",
            (code,)
        )
        await conn.commit()
    finally:
        await db_pool.release(conn)


async def get_all_managers() -> list:
    """Получить список всех менеджеров"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("""
            SELECT code, name, telegram_id, balance, partners_count, conversions 
            FROM managers 
            ORDER BY balance DESC
        """)
        rows = await cursor.fetchall()
        return [{
            "code": r[0],
            "name": r[1],
            "telegram_id": r[2],
            "balance": r[3] or 0,
            "partners_count": r[4] or 0,
            "conversions": r[5] or 0
        } for r in rows]
    finally:
        await db_pool.release(conn)


async def delete_manager(code: str) -> bool:
    """Удалить менеджера"""
    conn = await db_pool.acquire()
    try:
        await conn.execute("DELETE FROM managers WHERE code = ?", (code,))
        await conn.commit()
        return True
    finally:
        await db_pool.release(conn)


async def reset_manager_balance(code: str) -> float:
    """Сбросить баланс менеджера (после выплаты)"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT balance FROM managers WHERE code = ?", (code,))
        row = await cursor.fetchone()
        old_balance = row[0] if row else 0
        
        await conn.execute("UPDATE managers SET balance = 0 WHERE code = ?", (code,))
        await conn.commit()
        return old_balance
    finally:
        await db_pool.release(conn)


async def set_user_role(user_id: int, role: str, manager_code: str = None):
    """Установить роль пользователя (user/partner/manager)"""
    conn = await db_pool.acquire()
    try:
        if manager_code:
            await conn.execute(
                "UPDATE users SET role = ?, manager_id = ? WHERE id = ?",
                (role, manager_code, user_id)  # manager_id теперь хранит CODE, не ID
            )
        else:
            await conn.execute(
                "UPDATE users SET role = ? WHERE id = ?",
                (role, user_id)
            )
        await conn.commit()
        logger.info(f"User {user_id} role set to {role}" + (f" (manager: {manager_code})" if manager_code else ""))
    finally:
        await db_pool.release(conn)


async def get_user_role(user_id: int) -> str:
    """Получить роль пользователя"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT role FROM users WHERE id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] else "user"
    finally:
        await db_pool.release(conn)


async def get_user_manager(user_id: int) -> str:
    """Получить код менеджера партнёра"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT manager_id FROM users WHERE id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] else None  # Возвращает CODE
    finally:
        await db_pool.release(conn)


async def is_first_payment(user_id: int) -> bool:
    """Проверить, это первая оплата пользователя?"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT first_payment_done FROM users WHERE id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return not (row and row[0] == 1)
    finally:
        await db_pool.release(conn)


async def mark_first_payment_done(user_id: int):
    """Отметить что первая оплата сделана"""
    conn = await db_pool.acquire()
    try:
        await conn.execute(
            "UPDATE users SET first_payment_done = 1 WHERE id = ?", (user_id,)
        )
        await conn.commit()
    finally:
        await db_pool.release(conn)


async def process_referral_payment(user_id: int) -> dict:
    """
    Обработать реферальный платёж при ПЕРВОЙ оплате
    
    Returns:
        {
            'partner_id': ID партнёра или None,
            'partner_bonus': сумма партнёру ($10 или 0),
            'manager_code': код менеджера или None,
            'manager_bonus': сумма менеджеру ($3 или 0),
            'is_first': была ли это первая оплата
        }
    """
    result = {
        'partner_id': None,
        'partner_bonus': 0,
        'manager_code': None,
        'manager_bonus': 0,
        'is_first': False
    }
    
    # Проверяем первая ли это оплата
    if not await is_first_payment(user_id):
        logger.info(f"User {user_id}: renewal payment, no referral bonuses")
        return result
    
    result['is_first'] = True
    
    # Получаем кто пригласил (partner)
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT invited_by FROM users WHERE id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        partner_id = row[0] if row and row[0] else None
    finally:
        await db_pool.release(conn)
    
    if not partner_id:
        logger.info(f"User {user_id}: no referrer")
        await mark_first_payment_done(user_id)
        return result
    
    result['partner_id'] = partner_id
    
    # Начисляем партнёру $10
    await add_referral_bonus(partner_id, 10.0, user_id)
    result['partner_bonus'] = 10.0
    logger.info(f"Partner {partner_id} gets $10 for user {user_id}")
    
    # Получаем код менеджера партнёра
    manager_code = await get_user_manager(partner_id)
    
    if manager_code:
        result['manager_code'] = manager_code
        # Начисляем менеджеру $3 через таблицу managers
        await add_manager_bonus(manager_code, 3.0)
        result['manager_bonus'] = 3.0
        logger.info(f"Manager '{manager_code}' gets $3 for user {user_id}")
    
    # Отмечаем первую оплату
    await mark_first_payment_done(user_id)
    
    return result
    await mark_first_payment_done(user_id)
    
    return result


async def get_partners_list(manager_code: str = None) -> list:
    """Получить список партнёров (опционально фильтр по коду менеджера)"""
    conn = await db_pool.acquire()
    try:
        if manager_code:
            cursor = await conn.execute("""
                SELECT u.id, u.username, u.balance,
                       (SELECT COUNT(*) FROM users WHERE invited_by = u.id) as referrals,
                       (SELECT COUNT(*) FROM users WHERE invited_by = u.id AND first_payment_done = 1) as paid_referrals
                FROM users u
                WHERE u.role = 'partner' AND u.manager_id = ?
                ORDER BY u.balance DESC
            """, (manager_code,))
        else:
            cursor = await conn.execute("""
                SELECT u.id, u.username, u.balance, u.manager_id,
                       (SELECT COUNT(*) FROM users WHERE invited_by = u.id) as referrals,
                       (SELECT COUNT(*) FROM users WHERE invited_by = u.id AND first_payment_done = 1) as paid_referrals
                FROM users u
                WHERE u.role = 'partner'
                ORDER BY u.balance DESC
            """)
        
        rows = await cursor.fetchall()
        
        if manager_code:
            return [{
                "user_id": r[0],
                "username": r[1],
                "balance": r[2] or 0,
                "referrals": r[3],
                "paid_referrals": r[4]
            } for r in rows]
        else:
            return [{
                "user_id": r[0],
                "username": r[1],
                "balance": r[2] or 0,
                "manager_code": r[3],  # Это CODE
                "referrals": r[4],
                "paid_referrals": r[5]
            } for r in rows]
    finally:
        await db_pool.release(conn)


async def get_users_with_balance() -> list:
    """Получить всех пользователей с балансом > 0 для выплат"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("""
            SELECT id, username, balance, role 
            FROM users 
            WHERE balance > 0 
            ORDER BY balance DESC
        """)
        rows = await cursor.fetchall()
        return [{
            "user_id": r[0],
            "username": r[1],
            "balance": r[2],
            "role": r[3] or "user"
        } for r in rows]
    finally:
        await db_pool.release(conn)


# ==================== ТРИАЛ ====================
TRIAL_DAYS = 2  # Длительность пробного периода

async def can_use_trial(user_id: int) -> bool:
    """Проверить, может ли юзер использовать триал"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT trial_used FROM users WHERE id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row is None or row[0] != 1
    finally:
        await db_pool.release(conn)


async def activate_trial(user_id: int) -> bool:
    """
    Активировать триал для юзера
    
    Returns:
        True если триал активирован
        False если триал уже был использован
    """
    conn = await db_pool.acquire()
    try:
        # Проверяем не использован ли триал
        cursor = await conn.execute(
            "SELECT trial_used, paid FROM users WHERE id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        
        if row and row[0] == 1:
            logger.info(f"Trial already used for user {user_id}")
            return False
        
        if row and row[1] == 1:
            logger.info(f"User {user_id} already has paid access")
            return False
        
        # Активируем триал
        expiry = int((datetime.now().timestamp())) + (TRIAL_DAYS * 86400)
        
        await conn.execute("""
            UPDATE users 
            SET paid = 1, subscription_expiry = ?, trial_used = 1
            WHERE id = ?
        """, (expiry, user_id))
        await conn.commit()
        
        logger.info(f"✅ Trial activated for user {user_id} ({TRIAL_DAYS} days)")
        return True
    finally:
        await db_pool.release(conn)


async def get_users_by_lang(user_ids: list) -> dict:
    """
    Получить юзеров сгруппированных по языку
    
    Returns:
        {'ru': [id1, id2], 'en': [id3, id4]}
    """
    if not user_ids:
        return {'ru': [], 'en': []}
    
    conn = await db_pool.acquire()
    try:
        placeholders = ','.join('?' * len(user_ids))
        cursor = await conn.execute(
            f"SELECT id, language FROM users WHERE id IN ({placeholders})",
            user_ids
        )
        rows = await cursor.fetchall()
        
        result = {'ru': [], 'en': []}
        for user_id, lang in rows:
            if lang == 'en':
                result['en'].append(user_id)
            else:
                result['ru'].append(user_id)
        
        return result
    finally:
        await db_pool.release(conn)


async def get_user_by_username(username: str) -> dict:
    """
    Найти юзера по username
    
    Returns:
        {'user_id': 123, 'username': 'name', 'paid': 0/1} или None
    """
    # Убираем @ если есть
    username = username.lstrip('@').lower()
    
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute(
            "SELECT id, username, paid FROM users WHERE LOWER(username) = ?",
            (username,)
        )
        row = await cursor.fetchone()
        
        if row:
            return {
                'user_id': row[0],
                'username': row[1],
                'paid': row[2]
            }
        return None
    finally:
        await db_pool.release(conn)


async def get_referral_stats_full() -> dict:
    """Полная статистика по реферальной системе"""
    conn = await db_pool.acquire()
    try:
        # Менеджеры
        cursor = await conn.execute("SELECT COUNT(*) FROM users WHERE role = 'manager'")
        managers_count = (await cursor.fetchone())[0]
        
        # Партнёры
        cursor = await conn.execute("SELECT COUNT(*) FROM users WHERE role = 'partner'")
        partners_count = (await cursor.fetchone())[0]
        
        # Общий баланс к выплате
        cursor = await conn.execute("SELECT SUM(balance) FROM users WHERE balance > 0")
        total_pending = (await cursor.fetchone())[0] or 0
        
        # Конверсии (первые оплаты через рефералов)
        cursor = await conn.execute("""
            SELECT COUNT(*) FROM users 
            WHERE first_payment_done = 1 AND invited_by IS NOT NULL
        """)
        total_conversions = (await cursor.fetchone())[0]
        
        return {
            "managers_count": managers_count,
            "partners_count": partners_count,
            "total_pending": total_pending,
            "total_conversions": total_conversions
        }
    finally:
        await db_pool.release(conn)


# ==================== SIGNAL TRACKING ====================

async def add_active_signal(pair: str, side: str, signal_type: str, entry_price: float,
                           entry_min: float, entry_max: float,
                           tp1: float, tp2: float, tp3: float, stop_loss: float) -> int:
    """Добавить активный сигнал для отслеживания"""
    conn = await db_pool.acquire()
    try:
        created_ts = int(datetime.now().timestamp())
        cursor = await conn.execute("""
            INSERT INTO active_signals 
            (pair, side, signal_type, entry_price, entry_min, entry_max, tp1, tp2, tp3, stop_loss, created_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (pair, side, signal_type, entry_price, entry_min, entry_max, tp1, tp2, tp3, stop_loss, created_ts))
        await conn.commit()
        return cursor.lastrowid
    finally:
        await db_pool.release(conn)


async def get_active_signals() -> list:
    """Получить все активные сигналы для tracking"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("""
            SELECT id, pair, side, signal_type, entry_price, entry_min, entry_max,
                   tp1, tp2, tp3, stop_loss, entry_hit, tp1_hit, tp2_hit, tp3_hit, sl_hit, created_ts
            FROM active_signals
            WHERE status = 'active'
        """)
        rows = await cursor.fetchall()
        return [{
            'id': r[0], 'pair': r[1], 'side': r[2], 'signal_type': r[3],
            'entry_price': r[4], 'entry_min': r[5], 'entry_max': r[6],
            'tp1': r[7], 'tp2': r[8], 'tp3': r[9], 'stop_loss': r[10],
            'entry_hit': r[11], 'tp1_hit': r[12], 'tp2_hit': r[13],
            'tp3_hit': r[14], 'sl_hit': r[15], 'created_ts': r[16]
        } for r in rows]
    finally:
        await db_pool.release(conn)


async def get_active_signal_by_pair(pair: str, side: str) -> dict:
    """Получить активный сигнал по паре и направлению"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("""
            SELECT id, pair, side, signal_type, entry_price, entry_min, entry_max,
                   tp1, tp2, tp3, stop_loss
            FROM active_signals
            WHERE pair = ? AND side = ? AND status = 'active'
            ORDER BY created_ts DESC
            LIMIT 1
        """, (pair, side))
        row = await cursor.fetchone()
        
        if row:
            return {
                'id': row[0], 'pair': row[1], 'side': row[2], 'signal_type': row[3],
                'entry_price': row[4], 'entry_min': row[5], 'entry_max': row[6],
                'tp1': row[7], 'tp2': row[8], 'tp3': row[9], 'stop_loss': row[10]
            }
        return None
    finally:
        await db_pool.release(conn)


async def update_signal_status(signal_id: int, field: str, value: int = 1):
    """Обновить статус сигнала (entry_hit, tp1_hit, tp2_hit, tp3_hit, sl_hit)"""
    conn = await db_pool.acquire()
    try:
        await conn.execute(f"UPDATE active_signals SET {field} = ? WHERE id = ?", (value, signal_id))
        await conn.commit()
    finally:
        await db_pool.release(conn)


async def close_signal(signal_id: int, profit_percent: float = None):
    """Закрыть сигнал (по TP3 или SL)"""
    conn = await db_pool.acquire()
    try:
        closed_ts = int(datetime.now().timestamp())
        await conn.execute("""
            UPDATE active_signals 
            SET status = 'closed', closed_ts = ?, profit_percent = ?
            WHERE id = ?
        """, (closed_ts, profit_percent, signal_id))
        await conn.commit()
    finally:
        await db_pool.release(conn)


# ==================== SIGNAL HISTORY (антидублирование) ====================

async def add_signal_to_history(pair: str, side: str, signal_type: str, 
                                entry_price: float, confidence: float) -> int:
    """Добавить сигнал в историю"""
    conn = await db_pool.acquire()
    try:
        created_ts = int(datetime.now().timestamp())
        cursor = await conn.execute("""
            INSERT INTO signal_history 
            (pair, side, signal_type, entry_price, confidence, created_ts, sent_to_pro)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (pair, side, signal_type, entry_price, confidence, created_ts))
        await conn.commit()
        return cursor.lastrowid
    finally:
        await db_pool.release(conn)


async def mark_signal_sent_to_free(signal_id: int):
    """Отметить что сигнал отправлен FREE юзерам"""
    conn = await db_pool.acquire()
    try:
        free_send_ts = int(datetime.now().timestamp())
        await conn.execute("""
            UPDATE signal_history 
            SET sent_to_free = 1, free_send_ts = ?
            WHERE id = ?
        """, (free_send_ts, signal_id))
        await conn.commit()
    finally:
        await db_pool.release(conn)


async def get_pending_free_signals() -> list:
    """Получить сигналы для отправки FREE (MEDIUM, прошло 45 мин)"""
    from config import FREE_SIGNAL_DELAY
    
    conn = await db_pool.acquire()
    try:
        now = int(datetime.now().timestamp())
        delay_threshold = now - FREE_SIGNAL_DELAY
        
        cursor = await conn.execute("""
            SELECT id, pair, side, signal_type, entry_price, confidence, created_ts
            FROM signal_history
            WHERE signal_type = 'MEDIUM' 
              AND sent_to_free = 0 
              AND created_ts <= ?
            ORDER BY created_ts ASC
        """, (delay_threshold,))
        rows = await cursor.fetchall()
        return [{
            'id': r[0], 'pair': r[1], 'side': r[2], 'signal_type': r[3],
            'entry_price': r[4], 'confidence': r[5], 'created_ts': r[6]
        } for r in rows]
    finally:
        await db_pool.release(conn)


async def is_duplicate_signal(pair: str, side: str, entry_price: float, hours: int = 24) -> bool:
    """Проверить не дубликат ли сигнал (та же пара, направление, похожая цена за последние N часов)"""
    from config import PRICE_DUPLICATE_THRESHOLD
    
    conn = await db_pool.acquire()
    try:
        threshold_ts = int(datetime.now().timestamp()) - (hours * 3600)
        
        cursor = await conn.execute("""
            SELECT entry_price FROM signal_history
            WHERE pair = ? AND side = ? AND created_ts > ?
            ORDER BY created_ts DESC
            LIMIT 5
        """, (pair, side, threshold_ts))
        rows = await cursor.fetchall()
        
        for row in rows:
            old_price = row[0]
            price_diff = abs(entry_price - old_price) / old_price
            if price_diff < PRICE_DUPLICATE_THRESHOLD:
                return True
        
        return False
    finally:
        await db_pool.release(conn)


# ==================== DAILY SIGNAL COUNTS ====================

async def get_daily_counts() -> dict:
    """Получить счётчики сигналов за сегодня"""
    conn = await db_pool.acquire()
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        cursor = await conn.execute(
            "SELECT rare_count, high_count, medium_count, free_sent FROM daily_signal_counts WHERE date = ?",
            (today,)
        )
        row = await cursor.fetchone()
        
        if row:
            return {
                'rare': row[0], 'high': row[1], 
                'medium': row[2], 'free_sent': row[3]
            }
        return {'rare': 0, 'high': 0, 'medium': 0, 'free_sent': 0}
    finally:
        await db_pool.release(conn)


async def increment_daily_count(signal_type: str, is_free: bool = False):
    """Увеличить счётчик сигналов за день"""
    conn = await db_pool.acquire()
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Создаём запись если нет
        await conn.execute("""
            INSERT OR IGNORE INTO daily_signal_counts (date) VALUES (?)
        """, (today,))
        
        # Увеличиваем нужный счётчик
        if is_free:
            await conn.execute("""
                UPDATE daily_signal_counts SET free_sent = free_sent + 1 WHERE date = ?
            """, (today,))
        else:
            field = f"{signal_type.lower()}_count"
            await conn.execute(f"""
                UPDATE daily_signal_counts SET {field} = {field} + 1 WHERE date = ?
            """, (today,))
        
        await conn.commit()
    finally:
        await db_pool.release(conn)


async def can_send_signal(signal_type: str, is_free: bool = False) -> tuple:
    """
    Проверить можно ли отправить сигнал данного типа
    
    Returns:
        (can_send: bool, reason: str)
    """
    from config import (
        MAX_RARE_SIGNALS_PER_DAY, MAX_HIGH_SIGNALS_PER_DAY, 
        MAX_MEDIUM_SIGNALS_PER_DAY, FREE_MAX_SIGNALS_PER_DAY
    )
    
    counts = await get_daily_counts()
    
    if is_free:
        if counts['free_sent'] >= FREE_MAX_SIGNALS_PER_DAY:
            return False, f"FREE limit reached ({FREE_MAX_SIGNALS_PER_DAY}/day)"
        return True, "OK"
    
    if signal_type == 'RARE':
        if counts['rare'] >= MAX_RARE_SIGNALS_PER_DAY:
            return False, f"RARE limit reached ({MAX_RARE_SIGNALS_PER_DAY}/day)"
    elif signal_type == 'HIGH':
        if counts['high'] >= MAX_HIGH_SIGNALS_PER_DAY:
            return False, f"HIGH limit reached ({MAX_HIGH_SIGNALS_PER_DAY}/day)"
    elif signal_type == 'MEDIUM':
        if counts['medium'] >= MAX_MEDIUM_SIGNALS_PER_DAY:
            return False, f"MEDIUM limit reached ({MAX_MEDIUM_SIGNALS_PER_DAY}/day)"
    
    return True, "OK"


async def get_signals_sent_today() -> int:
    """Получить количество сигналов отправленных сегодня (для 'нет сигналов')"""
    counts = await get_daily_counts()
    return counts['rare'] + counts['high'] + counts['medium']


# ==================== FREE/PRO USER LISTS ====================

async def get_pro_users() -> list:
    """Получить список PRO юзеров (paid=1)"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT id FROM users WHERE paid = 1")
        rows = await cursor.fetchall()
        return [r[0] for r in rows]
    finally:
        await db_pool.release(conn)


async def get_free_users() -> list:
    """Получить список FREE юзеров (paid=0)"""
    conn = await db_pool.acquire()
    try:
        cursor = await conn.execute("SELECT id FROM users WHERE paid = 0 OR paid IS NULL")
        rows = await cursor.fetchall()
        return [r[0] for r in rows]
    finally:
        await db_pool.release(conn)
