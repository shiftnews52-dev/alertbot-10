#!/usr/bin/env python3
"""
import_history_FIXED.py - Импорт исторических данных (ИСПРАВЛЕНО)

ИСПРАВЛЕНИЯ:
- 1h: 300 свечей (было 300) ✓
- 4h: 200 свечей (было ~75) ✓✓ ВАЖНО!
- 1d: 100 свечей (было ~12) ✓✓ ВАЖНО!
"""
import sys
import asyncio
import httpx
from indicators import CANDLES

async def import_history(pair: str, tf: str, count: int):
    """Импортировать историю с Binance"""
    print(f"📥 Импорт {count} свечей {tf} для {pair}...")
    
    async with httpx.AsyncClient() as client:
        try:
            url = "https://api.binance.com/api/v3/klines"
            params = {
                "symbol": pair.upper(),
                "interval": tf,
                "limit": min(count, 1000)
            }
            
            print(f"  🔗 Запрос к Binance API...")
            resp = await client.get(url, params=params, timeout=10.0)
            resp.raise_for_status()
            
            klines = resp.json()
            print(f"  ✅ Получено {len(klines)} свечей {tf}")
            
            # Добавляем в хранилище
            added = 0
            for kline in klines:
                open_time = kline[0] / 1000
                candle = {
                    "ts": open_time,
                    "t": open_time,
                    "o": float(kline[1]),
                    "h": float(kline[2]),
                    "l": float(kline[3]),
                    "c": float(kline[4]),
                    "v": float(kline[5])
                }
                
                CANDLES.add_candle(pair.upper(), tf, candle)
                added += 1
            
            print(f"  ✅ Добавлено {added} свечей в хранилище")
            
            # Проверка
            total = len(CANDLES.get_candles(pair, tf))
            print(f"  📊 Всего свечей {tf} для {pair}: {total}")
            
            return True
            
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
            return False

async def import_all_default():
    """
    Импортировать все дефолтные пары для всех таймфреймов
    
    ИСПРАВЛЕНИЕ: Увеличено количество свечей для 4H и 1D
    """
    from config import DEFAULT_PAIRS
    
    print("=" * 80)
    print(f"📥 МАССОВЫЙ ИМПОРТ ИСТОРИЧЕСКИХ ДАННЫХ")
    print("=" * 80)
    print()
    print("📊 Конфигурация загрузки:")
    print("  • 1H: 300 свечей (~12.5 дней)")
    print("  • 4H: 200 свечей (~33 дня)")
    print("  • 1D: 100 свечей (~100 дней)")
    print()
    
    # ИСПРАВЛЕНИЕ: Новая конфигурация
    timeframes_config = {
        '1h': 300,
        '4h': 200,  # Было ~75, теперь 200!
        '1d': 100   # Было ~12, теперь 100!
    }
    
    total_success = 0
    total_failed = 0
    
    for pair in DEFAULT_PAIRS:
        print(f"\n🔄 Загрузка {pair}...")
        print("-" * 80)
        
        for tf, count in timeframes_config.items():
            success = await import_history(pair, tf, count)
            if success:
                total_success += 1
            else:
                total_failed += 1
                print(f"  ⚠️ Пропускаем {pair} {tf}")
            
            await asyncio.sleep(0.5)
    
    print()
    print("=" * 80)
    print("📊 ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 80)
    print()
    
    for pair in DEFAULT_PAIRS:
        candles_1h = len(CANDLES.get_candles(pair, "1h"))
        candles_4h = len(CANDLES.get_candles(pair, "4h"))
        candles_1d = len(CANDLES.get_candles(pair, "1d"))
        
        # Проверка достаточности
        status = "✅" if (candles_1h >= 100 and candles_4h >= 100 and candles_1d >= 30) else "❌"
        
        print(f"{status} {pair}:")
        print(f"   1H: {candles_1h} свечей")
        print(f"   4H: {candles_4h} свечей")
        print(f"   1D: {candles_1d} свечей")
        print()
    
    print("=" * 80)
    print(f"✅ Успешно: {total_success}")
    print(f"❌ Неудачно: {total_failed}")
    print("=" * 80)
    print()
    
    if total_failed == 0:
        print("🎉 ВСЕ ДАННЫЕ ЗАГРУЖЕНЫ!")
        print("   Теперь можно запустить бота: python main.py")
    else:
        print("⚠️  НЕКОТОРЫЕ ДАННЫЕ НЕ ЗАГРУЖЕНЫ")
        print("   Попробуй повторить импорт")

async def main():
    if len(sys.argv) < 2:
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║     ИМПОРТ ИСТОРИЧЕСКИХ ДАННЫХ (ИСПРАВЛЕННАЯ ВЕРСИЯ)        ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print()
        print("📋 Использование:")
        print()
        print("  1️⃣ Импорт одной пары и таймфрейма:")
        print("     python import_history_FIXED.py BTCUSDT 1h")
        print("     python import_history_FIXED.py ETHUSDT 4h")
        print()
        print("  2️⃣ Импорт всех дефолтных пар (РЕКОМЕНДУЕТСЯ):")
        print("     python import_history_FIXED.py all")
        print()
        print("💡 НОВАЯ КОНФИГУРАЦИЯ:")
        print("   • 1H: 300 свечей (~12.5 дней)")
        print("   • 4H: 200 свечей (~33 дня) ← УВЕЛИЧЕНО!")
        print("   • 1D: 100 свечей (~100 дней) ← УВЕЛИЧЕНО!")
        print()
        sys.exit(1)
    
    command = sys.argv[1].upper()
    
    print("=" * 80)
    print("📥 ИМПОРТ ИСТОРИЧЕСКИХ ДАННЫХ")
    print("=" * 80)
    print()
    
    if command == "ALL":
        await import_all_default()
    else:
        if len(sys.argv) < 3:
            print("❌ Укажи таймфрейм: 1h, 4h или 1d")
            print("   Пример: python import_history_FIXED.py BTCUSDT 4h")
            sys.exit(1)
        
        pair = sys.argv[1].upper()
        tf = sys.argv[2].lower()
        
        if tf not in ['1h', '4h', '1d']:
            print(f"❌ Неверный таймфрейм: {tf}")
            print("   Доступны: 1h, 4h, 1d")
            sys.exit(1)
        
        counts = {'1h': 300, '4h': 200, '1d': 100}
        count = counts[tf]
        
        success = await import_history(pair, tf, count)
        
        if success:
            print()
            print("=" * 80)
            print("✅ ИМПОРТ ЗАВЕРШЁН!")
            print("=" * 80)
        else:
            print()
            print("❌ Импорт не удался")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
