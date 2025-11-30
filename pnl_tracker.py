"""
pnl_tracker.py - Отслеживание реальных результатов сигналов и расчёт PnL
"""
import time
import asyncio
import logging
from typing import Optional, Dict, List
from datetime import datetime
import aiosqlite

from config import DB_PATH

logger = logging.getLogger(__name__)

# ==================== SQL SCHEMA ====================
PNL_SCHEMA = """
-- Таблица активных сигналов (ещё не закрытых)
CREATE TABLE IF NOT EXISTS active_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair TEXT NOT NULL,
    side TEXT NOT NULL,  -- LONG/SHORT
    entry_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit_1 REAL NOT NULL,
    take_profit_2 REAL NOT NULL,
    take_profit_3 REAL NOT NULL,
    score INTEGER NOT NULL,
    opened_ts INTEGER NOT NULL,
    tp1_hit INTEGER DEFAULT 0,
    tp2_hit INTEGER DEFAULT 0,
    tp3_hit INTEGER DEFAULT 0,
    sl_hit INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active'  -- active, closed
);

-- Таблица закрытых сигналов с результатами
CREATE TABLE IF NOT EXISTS closed_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL,
    pair TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    opened_ts INTEGER NOT NULL,
    closed_ts INTEGER NOT NULL,
    duration_hours REAL,
    result TEXT NOT NULL,  -- tp1, tp2, tp3, sl
    pnl_percent REAL NOT NULL,
    pnl_amount REAL,  -- если известна сумма позиции
    score INTEGER NOT NULL
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_active_pair ON active_signals(pair);
CREATE INDEX IF NOT EXISTS idx_active_status ON active_signals(status);
CREATE INDEX IF NOT EXISTS idx_closed_pair ON closed_signals(pair);
CREATE INDEX IF NOT EXISTS idx_closed_ts ON closed_signals(closed_ts);
"""

# ==================== PNL TRACKER CLASS ====================
class PnLTracker:
    """Класс для отслеживания PnL сигналов"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
    
    async def init_db(self):
        """Инициализация таблиц PnL"""
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.executescript(PNL_SCHEMA)
            await conn.commit()
        logger.info("PnL tracker initialized")
    
    async def add_signal(self, signal: Dict) -> int:
        """
        Добавить новый сигнал для отслеживания
        
        Args:
            signal: {
                'pair': 'BTCUSDT',
                'side': 'LONG',
                'price': 42000,
                'stop_loss': 41500,
                'take_profit_1': 42800,
                'take_profit_2': 43600,
                'take_profit_3': 44800,
                'score': 87
            }
        
        Returns:
            signal_id
        """
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                """INSERT INTO active_signals 
                (pair, side, entry_price, stop_loss, take_profit_1, 
                take_profit_2, take_profit_3, score, opened_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    signal['pair'],
                    signal['side'],
                    signal['price'],
                    signal['stop_loss'],
                    signal['take_profit_1'],
                    signal['take_profit_2'],
                    signal['take_profit_3'],
                    signal['score'],
                    int(time.time())
                )
            )
            await conn.commit()
            return cursor.lastrowid
    
    async def check_signal(self, signal_id: int, current_price: float) -> Optional[Dict]:
        """
        Проверить достигла ли цена TP/SL
        
        Returns:
            {'result': 'tp1/tp2/tp3/sl', 'pnl_percent': 2.5} или None
        """
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM active_signals WHERE id=? AND status='active'",
                (signal_id,)
            )
            signal = await cursor.fetchone()
            
            if not signal:
                return None
            
            side = signal['side']
            entry = signal['entry_price']
            
            # Для LONG
            if side == 'LONG':
                # Проверка SL (сначала!)
                if current_price <= signal['stop_loss'] and not signal['sl_hit']:
                    pnl = ((current_price - entry) / entry) * 100
                    await self._close_signal(conn, signal, current_price, 'sl', pnl)
                    return {'result': 'sl', 'pnl_percent': pnl}
                
                # Проверка TP3
                if current_price >= signal['take_profit_3'] and not signal['tp3_hit']:
                    pnl = ((current_price - entry) / entry) * 100
                    await self._close_signal(conn, signal, current_price, 'tp3', pnl)
                    return {'result': 'tp3', 'pnl_percent': pnl}
                
                # Проверка TP2
                if current_price >= signal['take_profit_2'] and not signal['tp2_hit']:
                    await self._mark_tp_hit(conn, signal_id, 'tp2')
                    pnl = ((signal['take_profit_2'] - entry) / entry) * 100
                    return {'result': 'tp2_partial', 'pnl_percent': pnl}
                
                # Проверка TP1
                if current_price >= signal['take_profit_1'] and not signal['tp1_hit']:
                    await self._mark_tp_hit(conn, signal_id, 'tp1')
                    pnl = ((signal['take_profit_1'] - entry) / entry) * 100
                    return {'result': 'tp1_partial', 'pnl_percent': pnl}
            
            # Для SHORT
            else:
                # Проверка SL (сначала!)
                if current_price >= signal['stop_loss'] and not signal['sl_hit']:
                    pnl = ((entry - current_price) / entry) * 100
                    await self._close_signal(conn, signal, current_price, 'sl', pnl)
                    return {'result': 'sl', 'pnl_percent': pnl}
                
                # Проверка TP3
                if current_price <= signal['take_profit_3'] and not signal['tp3_hit']:
                    pnl = ((entry - current_price) / entry) * 100
                    await self._close_signal(conn, signal, current_price, 'tp3', pnl)
                    return {'result': 'tp3', 'pnl_percent': pnl}
                
                # Проверка TP2
                if current_price <= signal['take_profit_2'] and not signal['tp2_hit']:
                    await self._mark_tp_hit(conn, signal_id, 'tp2')
                    pnl = ((entry - signal['take_profit_2']) / entry) * 100
                    return {'result': 'tp2_partial', 'pnl_percent': pnl}
                
                # Проверка TP1
                if current_price <= signal['take_profit_1'] and not signal['tp1_hit']:
                    await self._mark_tp_hit(conn, signal_id, 'tp1')
                    pnl = ((entry - signal['take_profit_1']) / entry) * 100
                    return {'result': 'tp1_partial', 'pnl_percent': pnl}
            
            return None
    
    async def _mark_tp_hit(self, conn, signal_id: int, tp: str):
        """Отметить что TP достигнут"""
        await conn.execute(
            f"UPDATE active_signals SET {tp}_hit=1 WHERE id=?",
            (signal_id,)
        )
        await conn.commit()
    
    async def _close_signal(self, conn, signal, exit_price: float, result: str, pnl_percent: float):
        """Закрыть сигнал и сохранить результат"""
        opened_ts = signal['opened_ts']
        closed_ts = int(time.time())
        duration_hours = (closed_ts - opened_ts) / 3600
        
        # Сохранить в closed_signals
        await conn.execute(
            """INSERT INTO closed_signals 
            (signal_id, pair, side, entry_price, exit_price, 
            opened_ts, closed_ts, duration_hours, result, pnl_percent, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal['id'],
                signal['pair'],
                signal['side'],
                signal['entry_price'],
                exit_price,
                opened_ts,
                closed_ts,
                duration_hours,
                result,
                pnl_percent,
                signal['score']
            )
        )
        
        # Обновить статус в active_signals
        await conn.execute(
            "UPDATE active_signals SET status='closed' WHERE id=?",
            (signal['id'],)
        )
        
        await conn.commit()
        logger.info(f"Signal {signal['id']} closed: {result}, PnL: {pnl_percent:.2f}%")
    
    async def get_statistics(self, days: int = 30) -> Dict:
        """
        Получить статистику за последние N дней
        
        Returns:
            {
                'total_signals': 50,
                'closed_signals': 45,
                'active_signals': 5,
                'winrate': 75.5,
                'avg_win': 4.2,
                'avg_loss': -2.1,
                'total_pnl': 67.3,
                'best_trade': 12.5,
                'worst_trade': -2.0,
                'avg_duration_hours': 8.5,
                'tp1_count': 10,
                'tp2_count': 15,
                'tp3_count': 20,
                'sl_count': 10
            }
        """
        from_ts = int(time.time()) - (days * 86400)
        
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            
            # Все закрытые сигналы за период
            cursor = await conn.execute(
                "SELECT * FROM closed_signals WHERE closed_ts >= ?",
                (from_ts,)
            )
            closed = await cursor.fetchall()
            
            # Активные сигналы
            cursor = await conn.execute(
                "SELECT COUNT(*) as cnt FROM active_signals WHERE status='active'"
            )
            active_count = (await cursor.fetchone())['cnt']
            
            if not closed:
                return {
                    'total_signals': active_count,
                    'closed_signals': 0,
                    'active_signals': active_count,
                    'winrate': 0,
                    'avg_win': 0,
                    'avg_loss': 0,
                    'total_pnl': 0,
                    'best_trade': 0,
                    'worst_trade': 0,
                    'avg_duration_hours': 0,
                    'tp1_count': 0,
                    'tp2_count': 0,
                    'tp3_count': 0,
                    'sl_count': 0
                }
            
            # Подсчёт статистики
            wins = [s for s in closed if s['pnl_percent'] > 0]
            losses = [s for s in closed if s['pnl_percent'] <= 0]
            
            tp1_count = len([s for s in closed if s['result'] == 'tp1'])
            tp2_count = len([s for s in closed if s['result'] == 'tp2'])
            tp3_count = len([s for s in closed if s['result'] == 'tp3'])
            sl_count = len([s for s in closed if s['result'] == 'sl'])
            
            total_pnl = sum(s['pnl_percent'] for s in closed)
            avg_win = sum(s['pnl_percent'] for s in wins) / len(wins) if wins else 0
            avg_loss = sum(s['pnl_percent'] for s in losses) / len(losses) if losses else 0
            winrate = (len(wins) / len(closed)) * 100 if closed else 0
            
            best_trade = max(s['pnl_percent'] for s in closed) if closed else 0
            worst_trade = min(s['pnl_percent'] for s in closed) if closed else 0
            avg_duration = sum(s['duration_hours'] for s in closed) / len(closed) if closed else 0
            
            return {
                'total_signals': len(closed) + active_count,
                'closed_signals': len(closed),
                'active_signals': active_count,
                'winrate': winrate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'total_pnl': total_pnl,
                'best_trade': best_trade,
                'worst_trade': worst_trade,
                'avg_duration_hours': avg_duration,
                'tp1_count': tp1_count,
                'tp2_count': tp2_count,
                'tp3_count': tp3_count,
                'sl_count': sl_count
            }
    
    async def get_pair_statistics(self, pair: str, days: int = 30) -> Dict:
        """Статистика по конкретной паре"""
        from_ts = int(time.time()) - (days * 86400)
        
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            
            cursor = await conn.execute(
                "SELECT * FROM closed_signals WHERE pair=? AND closed_ts >= ?",
                (pair, from_ts)
            )
            closed = await cursor.fetchall()
            
            if not closed:
                return {'pair': pair, 'signals': 0}
            
            wins = [s for s in closed if s['pnl_percent'] > 0]
            total_pnl = sum(s['pnl_percent'] for s in closed)
            winrate = (len(wins) / len(closed)) * 100
            
            return {
                'pair': pair,
                'signals': len(closed),
                'winrate': winrate,
                'total_pnl': total_pnl,
                'avg_pnl': total_pnl / len(closed)
            }
    
    async def get_active_signals(self) -> List[Dict]:
        """Получить все активные сигналы"""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM active_signals WHERE status='active'"
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

# Глобальный трекер
pnl_tracker = PnLTracker()
