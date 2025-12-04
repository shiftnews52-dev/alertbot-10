"""
professional_analyzer_STRICT.py - СТРОГАЯ версия для качественных сигналов

ИЗМЕНЕНИЯ:
1. min_confidence: 40 → 75 (нужно 4/5 условий)
2. price_distance_threshold: 5% → 1.5% (ближе к уровню)
3. Добавлен фильтр MTF confluence (тренд на всех TF)
4. Добавлен фильтр на дубликаты
5. Требуется подтверждение объёмом
6. Более строгий RSI фильтр

РЕЗУЛЬТАТ: 3-10 качественных сигналов в день вместо 44
"""
import logging
import time
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

# Кэш последних сигналов для предотвращения дубликатов
_signal_cache = {}  # {pair: {'side': 'LONG', 'timestamp': 123456, 'price': 42000}}
DUPLICATE_WINDOW = 4 * 3600  # 4 часа - не повторять сигнал для той же пары


class CryptoMickyAnalyzer:
    """
    СТРОГИЙ анализатор для качественных сигналов (3-10 в день)
    """
    
    def __init__(self):
        # ==================== СТРОГИЕ НАСТРОЙКИ ====================
        self.min_confidence = 75          # Было 40, теперь 75 (4/5 условий)
        self.price_distance_threshold = 1.5  # Было 5%, теперь 1.5%
        
        # Требуется MTF confluence
        self.require_mtf_confluence = True
        
        # Минимальное количество касаний уровня
        self.min_level_touches = 2
        
        # RSI фильтры (более строгие)
        self.rsi_oversold_max = 40      # Для LONG: RSI должен быть 30-40
        self.rsi_oversold_min = 25
        self.rsi_overbought_min = 60    # Для SHORT: RSI должен быть 60-70
        self.rsi_overbought_max = 75
        
        # Объём
        self.min_volume_ratio = 1.3     # Объём должен быть 130%+ от среднего
        
        self.long_conditions = [
            'price_at_support',
            'support_level_confirmed',
            'rsi_optimal',
            'volume_confirms',
            'mtf_confluence'
        ]
        
        self.short_conditions = [
            'price_at_resistance',
            'resistance_level_confirmed',
            'rsi_optimal',
            'volume_confirms',
            'mtf_confluence'
        ]
    
    def analyze_pair(self, pair: str, candles_1h: List, candles_4h: List, 
                     candles_1d: List, btc_candles_1h: List = None) -> Optional[Dict]:
        """
        Главный метод анализа со СТРОГИМИ фильтрами
        """
        try:
            # 1. Проверка данных
            if not self._validate_data(candles_1h, candles_4h, candles_1d):
                return None
            
            # 2. Проверка на дубликат
            if self._is_duplicate_signal(pair):
                logger.debug(f"⏭️ {pair}: Duplicate signal (within {DUPLICATE_WINDOW/3600:.0f}h window)")
                return None
            
            # 3. Анализ трендов на ВСЕХ таймфреймах
            trend_1h = self._determine_trend(candles_1h)
            trend_4h = self._determine_trend(candles_4h)
            trend_1d = self._determine_trend(candles_1d)
            
            logger.debug(f"{pair} Trends: 1H={trend_1h}, 4H={trend_4h}, 1D={trend_1d}")
            
            # 4. MTF Confluence - ОБЯЗАТЕЛЬНО совпадение трендов
            if self.require_mtf_confluence:
                mtf_result = self._check_mtf_confluence(trend_1h, trend_4h, trend_1d)
                if mtf_result is None:
                    logger.debug(f"⏭️ {pair}: No MTF confluence")
                    return None
                
                allowed_side, mtf_bonus = mtf_result
            else:
                allowed_side = None
                mtf_bonus = 0
            
            # 5. Поиск уровней
            supports = self._find_support_zones(candles_4h)
            resistances = self._find_resistance_zones(candles_4h)
            
            # 6. Анализ BTC (обязательно)
            btc_state = self._analyze_btc(btc_candles_1h) if btc_candles_1h else 'neutral'
            
            # 7. Проверяем LONG (только если MTF разрешает)
            if allowed_side in ['LONG', 'BOTH'] and trend_4h != 'bearish':
                # BTC должен быть нейтральным или бычьим для LONG
                if btc_state in ['neutral', 'bullish']:
                    long_signal = self._check_long_setup(
                        pair, candles_1h, candles_4h, supports, btc_state, mtf_bonus
                    )
                    if long_signal and long_signal['confidence'] >= self.min_confidence:
                        self._cache_signal(pair, 'LONG', long_signal['price'])
                        logger.info(f"✅ {pair} LONG signal: {long_signal['confidence']}%")
                        return long_signal
            
            # 8. Проверяем SHORT (только если MTF разрешает)
            if allowed_side in ['SHORT', 'BOTH'] and trend_4h != 'bullish':
                # BTC должен быть нейтральным или медвежьим для SHORT
                if btc_state in ['neutral', 'bearish']:
                    short_signal = self._check_short_setup(
                        pair, candles_1h, candles_4h, resistances, btc_state, mtf_bonus
                    )
                    if short_signal and short_signal['confidence'] >= self.min_confidence:
                        self._cache_signal(pair, 'SHORT', short_signal['price'])
                        logger.info(f"✅ {pair} SHORT signal: {short_signal['confidence']}%")
                        return short_signal
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing {pair}: {e}")
            return None
    
    def _is_duplicate_signal(self, pair: str) -> bool:
        """Проверка на дубликат сигнала"""
        if pair not in _signal_cache:
            return False
        
        cached = _signal_cache[pair]
        time_since = time.time() - cached['timestamp']
        
        return time_since < DUPLICATE_WINDOW
    
    def _cache_signal(self, pair: str, side: str, price: float):
        """Сохранить сигнал в кэш"""
        _signal_cache[pair] = {
            'side': side,
            'price': price,
            'timestamp': time.time()
        }
    
    def _check_mtf_confluence(self, trend_1h: str, trend_4h: str, trend_1d: str) -> Optional[Tuple[str, int]]:
        """
        Проверка Multi-Timeframe Confluence
        
        Returns:
            ('LONG'/'SHORT'/'BOTH', bonus_points) или None если нет confluence
        """
        trends = [trend_1h, trend_4h, trend_1d]
        
        # Идеальный случай: все 3 таймфрейма в одном направлении
        if all(t == 'bullish' for t in trends):
            return ('LONG', 25)  # +25 к confidence
        
        if all(t == 'bearish' for t in trends):
            return ('SHORT', 25)
        
        # Хороший случай: 2 из 3 таймфреймов совпадают, третий нейтральный
        bullish_count = trends.count('bullish')
        bearish_count = trends.count('bearish')
        neutral_count = trends.count('neutral') + trends.count('mixed')
        
        if bullish_count >= 2 and bearish_count == 0:
            return ('LONG', 15)
        
        if bearish_count >= 2 and bullish_count == 0:
            return ('SHORT', 15)
        
        # Нейтральный случай: все нейтральные (можно торговать обе стороны с осторожностью)
        if neutral_count >= 2 and bullish_count <= 1 and bearish_count <= 1:
            return ('BOTH', 5)
        
        # Конфликт трендов - НЕ торгуем
        return None
    
    def _determine_trend(self, candles: List) -> str:
        """
        СТРОГОЕ определение тренда (требуется 2/4 условий)
        """
        if len(candles) < 50:
            return 'mixed'
        
        closes = np.array([c['c'] for c in candles])
        
        bull_score = 0
        bear_score = 0
        
        # 1. Структура цены (Higher Highs / Lower Lows)
        recent_closes = closes[-20:]
        if self._check_higher_highs(recent_closes):
            bull_score += 1
        if self._check_lower_lows(recent_closes):
            bear_score += 1
        
        # 2. RSI
        rsi = self._calculate_rsi(closes)
        if rsi:
            if rsi > 55:
                bull_score += 1
            elif rsi < 45:
                bear_score += 1
        
        # 3. EMA alignment
        ema_20 = self._calculate_ema(closes, 20)
        ema_50 = self._calculate_ema(closes, 50)
        ema_100 = self._calculate_ema(closes, 100)
        
        if ema_20 and ema_50 and ema_100:
            if ema_20 > ema_50 > ema_100:
                bull_score += 1
            elif ema_20 < ema_50 < ema_100:
                bear_score += 1
        
        # 4. Цена относительно EMA
        if ema_50:
            if closes[-1] > ema_50 * 1.01:  # Цена выше EMA50 на 1%+
                bull_score += 1
            elif closes[-1] < ema_50 * 0.99:  # Цена ниже EMA50 на 1%+
                bear_score += 1
        
        # Требуется минимум 2 условия для определения тренда
        if bull_score >= 2 and bear_score == 0:
            return 'bullish'
        elif bear_score >= 2 and bull_score == 0:
            return 'bearish'
        elif bull_score == 0 and bear_score == 0:
            return 'neutral'
        else:
            return 'mixed'
    
    def _check_higher_highs(self, closes: np.ndarray) -> bool:
        """Проверка Higher Highs (восходящие максимумы)"""
        if len(closes) < 10:
            return False
        
        peaks = []
        for i in range(2, len(closes) - 2):
            if closes[i] > closes[i-1] and closes[i] > closes[i-2] and \
               closes[i] > closes[i+1] and closes[i] > closes[i+2]:
                peaks.append(closes[i])
        
        if len(peaks) < 2:
            return False
        
        # Последний пик выше предыдущего
        return peaks[-1] > peaks[-2]
    
    def _check_lower_lows(self, closes: np.ndarray) -> bool:
        """Проверка Lower Lows (нисходящие минимумы)"""
        if len(closes) < 10:
            return False
        
        troughs = []
        for i in range(2, len(closes) - 2):
            if closes[i] < closes[i-1] and closes[i] < closes[i-2] and \
               closes[i] < closes[i+1] and closes[i] < closes[i+2]:
                troughs.append(closes[i])
        
        if len(troughs) < 2:
            return False
        
        # Последний минимум ниже предыдущего
        return troughs[-1] < troughs[-2]
    
    def _find_support_zones(self, candles: List) -> List[Dict]:
        """Поиск зон поддержки с подсчётом касаний"""
        if len(candles) < 50:
            return []
        
        lows = np.array([c['l'] for c in candles])
        volumes = np.array([c['v'] for c in candles])
        
        # Ищем локальные минимумы
        local_lows = []
        for i in range(10, len(lows) - 10):
            if lows[i] <= lows[i-10:i].min() and lows[i] <= lows[i+1:i+11].min():
                local_lows.append({
                    'price': lows[i],
                    'index': i,
                    'volume': volumes[i]
                })
        
        if not local_lows:
            return []
        
        # Группируем близкие уровни (±2%)
        support_zones = []
        processed = set()
        
        for i, low1 in enumerate(local_lows):
            if i in processed:
                continue
            
            touches = [low1]
            processed.add(i)
            
            for j, low2 in enumerate(local_lows[i+1:], i+1):
                if j in processed:
                    continue
                
                # Если цены близки (в пределах 2%)
                if abs(low1['price'] - low2['price']) / low1['price'] < 0.02:
                    touches.append(low2)
                    processed.add(j)
            
            # Только уровни с минимум N касаниями
            if len(touches) >= self.min_level_touches:
                avg_price = np.mean([t['price'] for t in touches])
                total_volume = sum(t['volume'] for t in touches)
                
                support_zones.append({
                    'price': avg_price,
                    'touches': len(touches),
                    'volume': total_volume,
                    'strength': len(touches) * np.log1p(total_volume)
                })
        
        # Сортируем по силе уровня
        support_zones.sort(key=lambda x: x['strength'], reverse=True)
        
        return support_zones[:5]  # Топ 5 уровней
    
    def _find_resistance_zones(self, candles: List) -> List[Dict]:
        """Поиск зон сопротивления с подсчётом касаний"""
        if len(candles) < 50:
            return []
        
        highs = np.array([c['h'] for c in candles])
        volumes = np.array([c['v'] for c in candles])
        
        # Ищем локальные максимумы
        local_highs = []
        for i in range(10, len(highs) - 10):
            if highs[i] >= highs[i-10:i].max() and highs[i] >= highs[i+1:i+11].max():
                local_highs.append({
                    'price': highs[i],
                    'index': i,
                    'volume': volumes[i]
                })
        
        if not local_highs:
            return []
        
        # Группируем близкие уровни (±2%)
        resistance_zones = []
        processed = set()
        
        for i, high1 in enumerate(local_highs):
            if i in processed:
                continue
            
            touches = [high1]
            processed.add(i)
            
            for j, high2 in enumerate(local_highs[i+1:], i+1):
                if j in processed:
                    continue
                
                if abs(high1['price'] - high2['price']) / high1['price'] < 0.02:
                    touches.append(high2)
                    processed.add(j)
            
            if len(touches) >= self.min_level_touches:
                avg_price = np.mean([t['price'] for t in touches])
                total_volume = sum(t['volume'] for t in touches)
                
                resistance_zones.append({
                    'price': avg_price,
                    'touches': len(touches),
                    'volume': total_volume,
                    'strength': len(touches) * np.log1p(total_volume)
                })
        
        resistance_zones.sort(key=lambda x: x['strength'], reverse=True)
        
        return resistance_zones[:5]
    
    def _check_long_setup(self, pair: str, candles_1h: List, candles_4h: List,
                          supports: List[Dict], btc_state: str, mtf_bonus: int) -> Optional[Dict]:
        """Проверка условий для LONG со СТРОГИМИ фильтрами"""
        if not supports:
            return None
        
        current_price = candles_1h[-1]['c']
        closes = [c['c'] for c in candles_1h]
        
        for support in supports[:3]:  # Проверяем только топ-3 уровня
            level = support['price']
            
            # 1. Цена должна быть ОЧЕНЬ близко к уровню (1.5%)
            distance_pct = abs((current_price - level) / level * 100)
            if distance_pct > self.price_distance_threshold:
                continue
            
            conditions_met = []
            conditions_desc = []
            
            # Условие 1: Цена у поддержки
            conditions_met.append('price_at_support')
            conditions_desc.append(f"🎯 Цена у поддержки {level:.2f}$ (расстояние {distance_pct:.1f}%)")
            
            # Условие 2: Уровень подтверждён касаниями
            if support['touches'] >= self.min_level_touches:
                conditions_met.append('support_level_confirmed')
                conditions_desc.append(f"✅ Уровень подтверждён ({support['touches']} касаний)")
            
            # Условие 3: RSI в оптимальной зоне для LONG
            rsi = self._calculate_rsi(np.array(closes[-50:]), 14)
            if rsi and self.rsi_oversold_min <= rsi <= self.rsi_oversold_max:
                conditions_met.append('rsi_optimal')
                conditions_desc.append(f"📊 RSI оптимален ({rsi:.1f})")
            
            # Условие 4: Объём подтверждает
            if self._check_volume_confirmation(candles_1h, 'long'):
                conditions_met.append('volume_confirms')
                conditions_desc.append("📈 Объём подтверждает разворот")
            
            # Условие 5: MTF Confluence (уже проверено, добавляем если есть бонус)
            if mtf_bonus > 0:
                conditions_met.append('mtf_confluence')
                conditions_desc.append(f"🔄 Тренды совпадают (+{mtf_bonus}%)")
            
            # Проверяем минимальное количество условий
            if len(conditions_met) >= 4:  # Нужно минимум 4 из 5
                return self._create_signal(
                    pair, 'LONG', current_price, level, support['touches'],
                    conditions_met, conditions_desc, candles_1h, mtf_bonus
                )
        
        return None
    
    def _check_short_setup(self, pair: str, candles_1h: List, candles_4h: List,
                           resistances: List[Dict], btc_state: str, mtf_bonus: int) -> Optional[Dict]:
        """Проверка условий для SHORT со СТРОГИМИ фильтрами"""
        if not resistances:
            return None
        
        current_price = candles_1h[-1]['c']
        closes = [c['c'] for c in candles_1h]
        
        for resistance in resistances[:3]:
            level = resistance['price']
            
            distance_pct = abs((current_price - level) / level * 100)
            if distance_pct > self.price_distance_threshold:
                continue
            
            conditions_met = []
            conditions_desc = []
            
            # Условие 1: Цена у сопротивления
            conditions_met.append('price_at_resistance')
            conditions_desc.append(f"🎯 Цена у сопротивления {level:.2f}$ (расстояние {distance_pct:.1f}%)")
            
            # Условие 2: Уровень подтверждён
            if resistance['touches'] >= self.min_level_touches:
                conditions_met.append('resistance_level_confirmed')
                conditions_desc.append(f"✅ Уровень подтверждён ({resistance['touches']} касаний)")
            
            # Условие 3: RSI в оптимальной зоне для SHORT
            rsi = self._calculate_rsi(np.array(closes[-50:]), 14)
            if rsi and self.rsi_overbought_min <= rsi <= self.rsi_overbought_max:
                conditions_met.append('rsi_optimal')
                conditions_desc.append(f"📊 RSI оптимален ({rsi:.1f})")
            
            # Условие 4: Объём подтверждает
            if self._check_volume_confirmation(candles_1h, 'short'):
                conditions_met.append('volume_confirms')
                conditions_desc.append("📉 Объём подтверждает разворот")
            
            # Условие 5: MTF Confluence
            if mtf_bonus > 0:
                conditions_met.append('mtf_confluence')
                conditions_desc.append(f"🔄 Тренды совпадают (+{mtf_bonus}%)")
            
            if len(conditions_met) >= 4:
                return self._create_signal(
                    pair, 'SHORT', current_price, level, resistance['touches'],
                    conditions_met, conditions_desc, candles_1h, mtf_bonus
                )
        
        return None
    
    def _check_volume_confirmation(self, candles: List, side: str) -> bool:
        """
        Проверка подтверждения объёмом
        Для LONG: объём на зелёных свечах должен расти
        Для SHORT: объём на красных свечах должен расти
        """
        if len(candles) < 10:
            return False
        
        recent = candles[-10:]
        avg_volume = np.mean([c['v'] for c in candles[-30:]])
        
        if side == 'long':
            # Ищем зелёные свечи с повышенным объёмом
            green_candles = [c for c in recent if c['c'] > c['o']]
            if not green_candles:
                return False
            
            green_volume = np.mean([c['v'] for c in green_candles])
            return green_volume > avg_volume * self.min_volume_ratio
        else:
            # Ищем красные свечи с повышенным объёмом
            red_candles = [c for c in recent if c['c'] < c['o']]
            if not red_candles:
                return False
            
            red_volume = np.mean([c['v'] for c in red_candles])
            return red_volume > avg_volume * self.min_volume_ratio
    
    def _create_signal(self, pair: str, side: str, current_price: float,
                       level: float, level_strength: int, conditions_met: List[str],
                       conditions_desc: List[str], candles_1h: List, mtf_bonus: int) -> Dict:
        """Создание сигнала"""
        
        confidence = self._calculate_confidence(conditions_met, level_strength, mtf_bonus)
        entry_min, entry_max = self._calculate_entry_zone(side, level)
        stop_loss = self._calculate_stop_loss(side, level, candles_1h)
        tp1, tp2, tp3 = self._calculate_take_profits(side, current_price, level, candles_1h)
        position_size = self._calculate_position_size(confidence)
        
        return {
            'pair': pair,
            'side': side,
            'price': current_price,
            'confidence': confidence,
            'entry_zone': (entry_min, entry_max),
            'stop_loss': stop_loss,
            'take_profit_1': tp1,
            'take_profit_2': tp2,
            'take_profit_3': tp3,
            'position_size': position_size,
            'reasons': conditions_desc,
            'level': level,
            'conditions_met': len(conditions_met),
            'conditions_total': 5,
            'score': confidence  # Для совместимости
        }
    
    def _calculate_confidence(self, conditions_met: List[str], level_strength: int, mtf_bonus: int) -> int:
        """Расчёт Confidence Score"""
        # Базовый score: 15% за каждое условие
        base_score = len(conditions_met) * 15
        
        # Бонус за MTF confluence
        bonus = mtf_bonus
        
        # Бонус за сильный уровень (много касаний)
        if level_strength >= 4:
            bonus += 10
        elif level_strength >= 3:
            bonus += 5
        
        return min(base_score + bonus, 100)
    
    def _calculate_entry_zone(self, side: str, level: float) -> Tuple[float, float]:
        """Расчёт зоны входа (±0.5% от уровня)"""
        if side == 'LONG':
            entry_min = level * 0.995
            entry_max = level * 1.01
        else:
            entry_min = level * 0.99
            entry_max = level * 1.005
        
        return entry_min, entry_max
    
    def _calculate_stop_loss(self, side: str, level: float, candles: List) -> float:
        """Расчёт стоп-лосса на основе ATR"""
        atr_val = self._calculate_atr(candles)
        
        if side == 'LONG':
            return level - (atr_val * 1.5)  # 1.5 ATR под уровнем
        else:
            return level + (atr_val * 1.5)  # 1.5 ATR над уровнем
    
    def _calculate_take_profits(self, side: str, current_price: float, 
                                level: float, candles_1h: List) -> Tuple[float, float, float]:
        """Расчёт целей на основе ATR (R:R 2:1, 4:1, 6:1)"""
        atr_val = self._calculate_atr(candles_1h)
        
        if side == 'LONG':
            tp1 = current_price + (atr_val * 2)   # 2:1 R/R
            tp2 = current_price + (atr_val * 4)   # 4:1 R/R
            tp3 = current_price + (atr_val * 6)   # 6:1 R/R
        else:
            tp1 = current_price - (atr_val * 2)
            tp2 = current_price - (atr_val * 4)
            tp3 = current_price - (atr_val * 6)
        
        return tp1, tp2, tp3
    
    def _calculate_position_size(self, confidence: int) -> str:
        """Определение размера позиции"""
        if confidence >= 90:
            return "10-15% депо"
        elif confidence >= 80:
            return "7-10% депо"
        elif confidence >= 75:
            return "5-7% депо"
        else:
            return "3-5% депо"
    
    def _calculate_atr(self, candles: List, period: int = 14) -> float:
        """Расчёт ATR"""
        if len(candles) < period + 1:
            return 0
        
        true_ranges = []
        for i in range(1, len(candles)):
            high = candles[i]['h']
            low = candles[i]['l']
            prev_close = candles[i-1]['c']
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
        
        return np.mean(true_ranges[-period:])
    
    def _analyze_btc(self, btc_candles_1h: List) -> str:
        """Анализ состояния BTC"""
        if not btc_candles_1h or len(btc_candles_1h) < 24:
            return 'neutral'
        
        closes = np.array([c['c'] for c in btc_candles_1h])
        
        # Изменение за последние 4 часа
        change_4h = (closes[-1] - closes[-4]) / closes[-4] * 100
        
        # Изменение за последние 24 часа
        change_24h = (closes[-1] - closes[-24]) / closes[-24] * 100
        
        # BTC bullish если растёт на обоих таймфреймах
        if change_4h > 0.5 and change_24h > 1:
            return 'bullish'
        elif change_4h < -0.5 and change_24h < -1:
            return 'bearish'
        else:
            return 'neutral'
    
    def _calculate_rsi(self, closes: np.ndarray, period: int = 14) -> Optional[float]:
        """Расчёт RSI"""
        if len(closes) < period + 1:
            return None
        
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_ema(self, values: np.ndarray, period: int) -> Optional[float]:
        """Расчёт EMA"""
        if len(values) < period:
            return None
        
        k = 2 / (period + 1)
        ema = values[0]
        for value in values[1:]:
            ema = value * k + ema * (1 - k)
        return ema
    
    def _validate_data(self, candles_1h: List, candles_4h: List, candles_1d: List) -> bool:
        """Проверка достаточности данных"""
        return (
            len(candles_1h) >= 100 and
            len(candles_4h) >= 100 and
            len(candles_1d) >= 30
        )


# Глобальный экземпляр анализатора
crypto_micky_analyzer = CryptoMickyAnalyzer()
