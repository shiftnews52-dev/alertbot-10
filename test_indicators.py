#!/usr/bin/env python3
"""
test_indicators.py - Тестирование индикаторов
Запуск: python test_indicators.py
"""
import sys
from indicators import (
    ema, sma, rsi, macd, bollinger_bands, 
    volume_strength, atr, calculate_tp_sl
)

def test_ema():
    """Тест EMA"""
    print("🧪 Тест EMA...")
    closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110]
    result = ema(closes, 9)
    
    assert result is not None, "EMA не должна быть None"
    assert 100 < result < 120, f"EMA вне ожидаемого диапазона: {result}"
    print(f"   ✅ EMA(9) = {result:.2f}")

def test_rsi():
    """Тест RSI"""
    print("🧪 Тест RSI...")
    # Восходящий тренд
    closes = list(range(50, 80))
    result = rsi(closes, 14)
    
    assert result is not None, "RSI не должен быть None"
    assert 0 <= result <= 100, f"RSI вне диапазона 0-100: {result}"
    assert result > 50, "RSI должен быть > 50 на восходящем тренде"
    print(f"   ✅ RSI(14) = {result:.1f}")

def test_macd():
    """Тест MACD"""
    print("🧪 Тест MACD...")
    closes = list(range(100, 160))
    result = macd(closes)
    
    assert result is not None, "MACD не должен быть None"
    macd_line, signal_line, histogram = result
    assert histogram == macd_line - signal_line, "Гистограмма = MACD - Signal"
    print(f"   ✅ MACD = {macd_line:.2f}, Signal = {signal_line:.2f}, Hist = {histogram:.2f}")

def test_bollinger_bands():
    """Тест Bollinger Bands"""
    print("🧪 Тест Bollinger Bands...")
    closes = [100] * 20 + [105, 110, 115]  # Стабильная цена, потом рост
    result = bollinger_bands(closes)
    
    assert result is not None, "BB не должен быть None"
    upper, middle, lower = result
    assert upper > middle > lower, "Upper > Middle > Lower"
    print(f"   ✅ BB: Upper={upper:.2f}, Middle={middle:.2f}, Lower={lower:.2f}")

def test_volume_strength():
    """Тест Volume Strength"""
    print("🧪 Тест Volume Strength...")
    candles = [{"v": 1000} for _ in range(20)]
    candles.append({"v": 3000})  # Резкий рост объёма
    
    result = volume_strength(candles, 20)
    assert result is not None, "Volume strength не должен быть None"
    assert result > 2.5, f"Volume strength должен быть > 2.5 (текущий: {result:.2f})"
    print(f"   ✅ Volume Strength = {result:.1f}x")

def test_atr():
    """Тест ATR"""
    print("🧪 Тест ATR...")
    candles = [
        {"h": 105, "l": 95, "c": 100},
        {"h": 110, "l": 100, "c": 105},
        {"h": 115, "l": 105, "c": 110},
    ] * 5  # 15 свечей
    
    result = atr(candles, 14)
    assert result is not None, "ATR не должен быть None"
    assert result > 0, "ATR должен быть положительным"
    print(f"   ✅ ATR(14) = {result:.2f}")

def test_calculate_tp_sl():
    """Тест расчёта TP/SL"""
    print("🧪 Тест TP/SL...")
    
    # LONG позиция
    entry = 100.0
    atr_val = 2.0
    result = calculate_tp_sl(entry, "LONG", atr_val)
    
    assert result["stop_loss"] < entry, "SL должен быть ниже входа для LONG"
    assert result["take_profit_1"] > entry, "TP1 должен быть выше входа для LONG"
    assert result["take_profit_2"] > result["take_profit_1"], "TP2 > TP1"
    assert result["take_profit_3"] > result["take_profit_2"], "TP3 > TP2"
    
    print(f"   ✅ LONG @ {entry}")
    print(f"      SL:  {result['stop_loss']:.2f} (-{result['sl_percent']:.2f}%)")
    print(f"      TP1: {result['take_profit_1']:.2f} (+{result['tp1_percent']:.2f}%)")
    print(f"      TP2: {result['take_profit_2']:.2f} (+{result['tp2_percent']:.2f}%)")
    print(f"      TP3: {result['take_profit_3']:.2f} (+{result['tp3_percent']:.2f}%)")
    
    # SHORT позиция
    result = calculate_tp_sl(entry, "SHORT", atr_val)
    assert result["stop_loss"] > entry, "SL должен быть выше входа для SHORT"
    assert result["take_profit_1"] < entry, "TP1 должен быть ниже входа для SHORT"
    print(f"   ✅ SHORT @ {entry}")
    print(f"      SL:  {result['stop_loss']:.2f} (+{result['sl_percent']:.2f}%)")
    print(f"      TP1: {result['take_profit_1']:.2f} (-{result['tp1_percent']:.2f}%)")

def run_all_tests():
    """Запустить все тесты"""
    print("=" * 50)
    print("🧪 Тестирование индикаторов")
    print("=" * 50)
    print()
    
    tests = [
        test_ema,
        test_rsi,
        test_macd,
        test_bollinger_bands,
        test_volume_strength,
        test_atr,
        test_calculate_tp_sl
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"   ❌ Тест провален: {e}")
            failed += 1
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            failed += 1
        print()
    
    print("=" * 50)
    print(f"✅ Пройдено: {passed}")
    print(f"❌ Провалено: {failed}")
    print("=" * 50)
    
    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)