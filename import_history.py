#!/usr/bin/env python3
"""
import_history.py - Импорт исторических данных (ТОЛЬКО 1H)
Использование: 
    python import_history.py BTCUSDT
    python import_history.py all
"""
import sys
import asyncio
import httpx
from indicators import CANDLES

async def import_history(pair: str, count: int = 300):
    """Импортировать историю с Binance для 1h"""
    print(f"📥 Импорт {count} часовых свечей для {pair}...")
    
    async with httpx.AsyncClient() as client:
        try:
            # Binance Klines API
            url = "https://api.binance.com/api/v3/klines"
            params = {
                "symbol": pair.upper(),
                "interval": "1h",  # Фиксированный часовой таймфрейм
                "limit": min(count, 1000)
            }
            
            print(f"  🔗 Запрос к Binance API...")
            resp = await client.get(url, params=params, timeout=10.0)
            resp.raise_for_status()
            
            klines = resp.json()
            print(f"  ✅ Получено {len(klines)} часовых свечей")
            
            # Очищаем старые данные
            CANDLES.candles[pair.upper()].clear()
            
            # Добавляем в хранилище
            added = 0
            for kline in klines:
                open_time = kline[0] / 1000  # ms -> s
                open_price = float(kline[1])
                high_price = float(kline[2])
                low_price = float(kline[3])
                close_price = float(kline[4])
                volume = float(kline[5])
                
                # Bucket для часового таймфрейма (3600 секунд)
                bucket = int(open_time // 3600) * 3600
                
                candle = {
                    "ts": bucket,
                    "o": open_price,
                    "h": high_price,
                    "l": low_price,
                    "c": close_price,
                    "v": volume
                }
                
                CANDLES.candles[pair.upper()].append(candle)
                added += 1
            
            print(f"  ✅ Добавлено {added} свечей в хранилище")
            
            # Проверка
            total = len(CANDLES.get_candles(pair))
            print(f"  📊 Всего свечей для {pair}: {total}")
            
            if total >= 250:
                print(f"  ✅ Достаточно данных для анализа!")
            else:
                print(f"  ⚠️ Нужно ещё {250 - total} свечей")
            
            # Статистика
            closes = [c["c"] for c in CANDLES.get_candles(pair)]
            if closes:
                print(f"  📈 Диапазон цен: {min(closes):.2f} - {max(closes):.2f}")
                print(f"  📊 Текущая цена: {closes[-1]:.2f}")
            
            return True
            
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
            return False

async def import_all_default(count: int = 300):
    """Импортировать все дефолтные пары"""
    from config import DEFAULT_PAIRS
    
    print("=" * 60)
    print(f"📥 МАССОВЫЙ ИМПОРТ (1h)")
    print("=" * 60)
    print()
    
    for pair in DEFAULT_PAIRS:
        success = await import_history(pair, count)
        if not success:
            print(f"  ⚠️ Пропускаем {pair}")
        print()
        await asyncio.sleep(0.5)
    
    print("=" * 60)
    print("✅ МАССОВЫЙ ИМПОРТ ЗАВЕРШЁН!")
    print("=" * 60)

async def main():
    if len(sys.argv) < 2:
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║          ИМПОРТ ИСТОРИЧЕСКИХ ДАННЫХ (1H ТОЛЬКО)             ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print()
        print("📋 Использование:")
        print()
        print("  1️⃣ Импорт одной пары:")
        print("     python import_history.py BTCUSDT")
        print("     python import_history.py ETHUSDT")
        print()
        print("  2️⃣ Импорт всех дефолтных пар:")
        print("     python import_history.py all")
        print()
        print("💡 По умолчанию импортируется 300 часовых свечей (~12.5 дней)")
        print()
        sys.exit(1)
    
    pair = sys.argv[1].upper()
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    
    print("=" * 60)
    print("📥 ИМПОРТ ИСТОРИЧЕСКИХ ДАННЫХ")
    print("=" * 60)
    print()
    
    if pair == "ALL":
        await import_all_default(count)
    else:
        success = await import_history(pair, count)
        
        if success:
            print()
            print("=" * 60)
            print("✅ ИМПОРТ ЗАВЕРШЁН!")
            print("=" * 60)
            print()
            print("💡 Теперь можно:")
            print("   1. Запустить бота: python main.py")
            print("   2. Или протестировать: python test_indicators.py")
        else:
            print()
            print("❌ Импорт не удался")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
