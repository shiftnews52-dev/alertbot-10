"""
professional_analyzer_FIXED.py - Исправленная версия с более мягкими условиями
"""
import logging
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

class CryptoMickyAnalyzer:
    """
    ИСПРАВЛЕНИЯ для увеличения количества сигналов:
    1. min_confidence снижен с 60% до 40% (2/5 условий вместо 3/5)
    2. Увеличена зона поиска уровня с ±2% до ±5%
    3. Убран фильтр на mixed trend
    4. Увеличено количество загружаемых свечей 4H с 50 до 200
    5. Смягчены условия для определения тренда (достаточно 1/4 вместо 2/4)
    """
    
    def __init__(self):
        # ИСПРАВЛЕНИЕ #1: Снижен порог confidence с 60% до 40%
        self.min_confidence = 40  # Теперь достаточно 2/5 условий
        
        # ИСПРАВЛЕНИЕ #2: Увеличена зона поиска уровня
        self.price_distance_threshold = 5.0  # Было 2.0%, стало 5.0%
        
        self.long_conditions = [
            'price_at_support',
            'support_level_confirmed',
            'rsi_bullish',
            'volume_weakness',
            'btc_neutral_or_up'
        ]
        
        self.short_conditions = [
            'price_at_resistance',
            'resistance_level_confirmed',
            'rsi_bearish',
            'volume_weakness',
            'btc_neutral_or_down'
        ]
    
    def analyze_pair(self, pair: str, candles_1h: List, candles_4h: List, 
                     candles_1d: List, btc_candles_1h: List = None) -> Optional[Dict]:
        """Главный метод анализа с исправлениями"""
        try:
            if not self._validate_data(candles_1h, candles_4h, candles_1d):
                return None
            
            # Анализ тренда
            trend_4h = self._determine_trend(candles_4h)
            trend_1d = self._determine_trend(candles_1d)
            
            logger.debug(f"{pair} Trends: 4H={trend_4h}, 1D={trend_1d}")
            
            # ИСПРАВЛЕНИЕ #3: УБРАН фильтр на mixed trend
            # Теперь анализируем даже при mixed trend
            
            # Поиск уровней
            supports = self._find_support_zones(candles_4h)
            resistances = self._find_resistance_zones(candles_4h)
            
            logger.debug(f"{pair} Levels: {len(supports)} supports, {len(resistances)} resistances")
            
            # Анализ BTC
            btc_state = self._analyze_btc(btc_candles_1h) if btc_candles_1h else 'neutral'
            
            # Проверяем LONG
            if trend_4h != 'bearish' or trend_1d != 'bearish':
                long_signal = self._check_long_setup(
                    pair, candles_1h, candles_4h, supports, btc_state
                )
                if long_signal and long_signal['confidence'] >= self.min_confidence:
                    logger.info(f"✅ {pair} LONG signal: {long_signal['confidence']}%")
                    return long_signal
            
            # Проверяем SHORT
            if trend_4h != 'bullish' or trend_1d != 'bullish':
                short_signal = self._check_short_setup(
                    pair, candles_1h, candles_4h, resistances, btc_state
                )
                if short_signal and short_signal['confidence'] >= self.min_confidence:
                    logger.info(f"✅ {pair} SHORT signal: {short_signal['confidence']}%")
                    return short_signal
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing {pair}: {e}")
            return None
    
    def _determine_trend(self, candles: List) -> str:
        """
        ИСПРАВЛЕНИЕ #5: Смягчены условия определения тренда
        Теперь достаточно 1/4 условий вместо 2/4
        """
        if len(candles) < 50:
            return 'mixed'
        
        closes = np.array([c['c'] for c in candles])
        
        bull_score = 0
        bear_score = 0
        
        # 1. Структура цены
        recent_closes = closes[-20:]
        if self._check_higher_highs(recent_closes):
            bull_score += 1
        if self._check_lower_lows(recent_closes):
            bear_score += 1
        
        # 2. RSI
        rsi = self._calculate_rsi(closes)
        if rsi:
            if rsi > 50:
                bull_score += 1
            elif rsi < 50:
                bear_score += 1
        
        # 3. EMA
        ema_50 = self._calculate_ema(closes, 50)
        ema_100 = self._calculate_ema(closes, 100)
        if ema_50 and ema_100:
            if closes[-1] > ema_50 and closes[-1] > ema_100:
                bull_score += 1
            elif closes[-1] < ema_50 and closes[-1] < ema_100:
                bear_score += 1
        
        # 4. Объёмы
        if self._check_volume_trend(candles, 'up'):
            bull_score += 1
        if self._check_volume_trend(candles, 'down'):
            bear_score += 1
        
        # ИСПРАВЛЕНИЕ: Теперь достаточно 1 условия вместо 2
        if bull_score >= 1 and bear_score == 0:
            return 'bullish'
        elif bear_score >= 1 and bull_score == 0:
            return 'bearish'
        else:
            return 'mixed'
    
    def _check_higher_highs(self, closes: np.ndarray) -> bool:
        """Проверка higher highs"""
        if len(closes) < 10:
            return False
        peaks = []
        for i in range(5, len(closes)-5):
            if closes[i] > closes[i-5:i].max() and closes[i] > closes[i+1:i+6].max():
                peaks.append(closes[i])
        return len(peaks) >= 2 and peaks[-1] > peaks[0]
    
    def _check_lower_lows(self, closes: np.ndarray) -> bool:
        """Проверка lower lows"""
        if len(closes) < 10:
            return False
        troughs = []
        for i in range(5, len(closes)-5):
            if closes[i] < closes[i-5:i].min() and closes[i] < closes[i+1:i+6].min():
                troughs.append(closes[i])
        return len(troughs) >= 2 and troughs[-1] < troughs[0]
    
    def _check_volume_trend(self, candles: List, direction: str) -> bool:
        """Проверка объёмов на движениях"""
        if len(candles) < 20:
            return False
        
        recent = candles[-10:]
        up_volumes = []
        down_volumes = []
        
        for candle in recent:
            if candle['c'] > candle['o']:
                up_volumes.append(candle['v'])
            else:
                down_volumes.append(candle['v'])
        
        if not up_volumes or not down_volumes:
            return False
        
        avg_up = np.mean(up_volumes)
        avg_down = np.mean(down_volumes)
        
        if direction == 'up':
            return avg_up > avg_down * 1.2
        else:
            return avg_down > avg_up * 1.2
    
    def _find_support_zones(self, candles: List) -> List[Dict]:
        """Поиск зон поддержки"""
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
        
        # Группируем близкие уровни (±3%)
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
                
                price_diff_pct = abs((low1['price'] - low2['price']) / low1['price'] * 100)
                if price_diff_pct <= 3.0:  # Было 2.0%, увеличено до 3.0%
                    touches.append(low2)
                    processed.add(j)
            
            if len(touches) >= 2:  # Минимум 2 касания
                avg_price = np.mean([t['price'] for t in touches])
                avg_volume = np.mean([t['volume'] for t in touches])
                
                support_zones.append({
                    'price': avg_price,
                    'touches': len(touches),
                    'avg_volume': avg_volume,
                    'strength': len(touches)
                })
        
        # Сортируем по силе
        support_zones.sort(key=lambda x: x['strength'], reverse=True)
        return support_zones
    
    def _find_resistance_zones(self, candles: List) -> List[Dict]:
        """Поиск зон сопротивления"""
        if len(candles) < 50:
            return []
        
        highs = np.array([c['h'] for c in candles])
        volumes = np.array([c['v'] for c in candles])
        
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
                
                price_diff_pct = abs((high1['price'] - high2['price']) / high1['price'] * 100)
                if price_diff_pct <= 3.0:
                    touches.append(high2)
                    processed.add(j)
            
            if len(touches) >= 2:
                avg_price = np.mean([t['price'] for t in touches])
                avg_volume = np.mean([t['volume'] for t in touches])
                
                resistance_zones.append({
                    'price': avg_price,
                    'touches': len(touches),
                    'avg_volume': avg_volume,
                    'strength': len(touches)
                })
        
        resistance_zones.sort(key=lambda x: x['strength'], reverse=True)
        return resistance_zones
    
    def _check_long_setup(self, pair: str, candles_1h: List, candles_4h: List,
                          supports: List[Dict], btc_state: str) -> Optional[Dict]:
        """Проверка условий для LONG"""
        if not supports:
            return None
        
        current_price = candles_1h[-1]['c']
        
        for support in supports[:5]:  # Проверяем топ-5 уровней
            level = support['price']
            
            # ИСПРАВЛЕНИЕ #2: Увеличена зона с ±2% до ±5%
            distance_pct = abs((current_price - level) / level * 100)
            
            if distance_pct > self.price_distance_threshold:
                continue
            
            conditions_met = []
            conditions_desc = []
            
            # 1. Цена у поддержки
            conditions_met.append('price_at_support')
            conditions_desc.append(f"Цена у поддержки {level:.2f}$")
            
            # 2. Подтверждённый уровень
            if support['touches'] >= 2:
                conditions_met.append('support_level_confirmed')
                conditions_desc.append(f"Уровень подтверждён ({support['touches']} касаний)")
            
            # 3. RSI бычий
            closes = [c['c'] for c in candles_1h]
            rsi = self._calculate_rsi(closes[-50:], 14)
            if rsi and 30 <= rsi <= 50:  # Расширено с 30-45 до 30-50
                conditions_met.append('rsi_bullish')
                conditions_desc.append(f"RSI бычий ({rsi:.1f})")
            
            # 4. Объёмы падают на красных
            if self._volume_decreasing_on_bearish(candles_1h):
                conditions_met.append('volume_weakness')
                conditions_desc.append("Объёмы падают на красных")
            
            # 5. BTC нейтрален или растёт
            if btc_state in ['neutral', 'bullish']:
                conditions_met.append('btc_neutral_or_up')
                conditions_desc.append(f"BTC {btc_state}")
            
            # ИСПРАВЛЕНИЕ #1: Теперь достаточно 2/5 условий
            if len(conditions_met) >= 2:
                return self._create_signal(
                    pair, 'LONG', current_price, level, support['touches'],
                    conditions_met, conditions_desc, candles_1h
                )
        
        return None
    
    def _check_short_setup(self, pair: str, candles_1h: List, candles_4h: List,
                           resistances: List[Dict], btc_state: str) -> Optional[Dict]:
        """Проверка условий для SHORT"""
        if not resistances:
            return None
        
        current_price = candles_1h[-1]['c']
        
        for resistance in resistances[:5]:
            level = resistance['price']
            
            distance_pct = abs((current_price - level) / level * 100)
            
            if distance_pct > self.price_distance_threshold:
                continue
            
            conditions_met = []
            conditions_desc = []
            
            conditions_met.append('price_at_resistance')
            conditions_desc.append(f"Цена у сопротивления {level:.2f}$")
            
            if resistance['touches'] >= 2:
                conditions_met.append('resistance_level_confirmed')
                conditions_desc.append(f"Уровень подтверждён ({resistance['touches']} касаний)")
            
            closes = [c['c'] for c in candles_1h]
            rsi = self._calculate_rsi(closes[-50:], 14)
            if rsi and 50 <= rsi <= 70:  # Расширено с 55-70 до 50-70
                conditions_met.append('rsi_bearish')
                conditions_desc.append(f"RSI медвежий ({rsi:.1f})")
            
            if self._volume_decreasing_on_bullish(candles_1h):
                conditions_met.append('volume_weakness')
                conditions_desc.append("Объёмы падают на зелёных")
            
            if btc_state in ['neutral', 'bearish']:
                conditions_met.append('btc_neutral_or_down')
                conditions_desc.append(f"BTC {btc_state}")
            
            if len(conditions_met) >= 2:
                return self._create_signal(
                    pair, 'SHORT', current_price, level, resistance['touches'],
                    conditions_met, conditions_desc, candles_1h
                )
        
        return None
    
    def _create_signal(self, pair: str, side: str, current_price: float,
                      level: float, level_strength: int, conditions_met: List[str],
                      conditions_desc: List[str], candles_1h: List) -> Dict:
        """Создание сигнала"""
        
        confidence = self._calculate_confidence(conditions_met, level_strength)
        entry_min, entry_max = self._calculate_entry_zone(side, level)
        stop_loss = self._calculate_stop_loss(side, level)
        tp1, tp2, tp3 = self._calculate_take_profits(side, current_price, level, candles_1h)
        position_size = self._calculate_position_size(confidence)
        
        # Форматируем reasons для вывода
        reasons = []
        for desc in conditions_desc:
            reasons.append(desc)
        
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
            'reasons': reasons,
            'level': level,
            'conditions_met': len(conditions_met),
            'conditions_total': 5
        }
    
    def _calculate_confidence(self, conditions_met: List[str], level_strength: int) -> int:
        """Расчёт Confidence Score"""
        base_score = len(conditions_met) * 20
        
        bonus = 0
        if len(conditions_met) == 5:
            bonus += 10
        if level_strength >= 3:
            bonus += 10
        
        return min(base_score + bonus, 100)
    
    def _calculate_entry_zone(self, side: str, level: float) -> Tuple[float, float]:
        """Расчёт зоны входа"""
        if side == 'LONG':
            entry_min = level * 0.995
            entry_max = level * 1.015
        else:
            entry_min = level * 0.985
            entry_max = level * 1.005
        
        return entry_min, entry_max
    
    def _calculate_stop_loss(self, side: str, level: float) -> float:
        """Расчёт стоп-лосса"""
        if side == 'LONG':
            return level * 0.985
        else:
            return level * 1.015
    
    def _calculate_take_profits(self, side: str, current_price: float, 
                                level: float, candles_1h: List) -> Tuple[float, float, float]:
        """Расчёт 3 целей"""
        closes = np.array([c['c'] for c in candles_1h])
        highs = np.array([c['h'] for c in candles_1h])
        lows = np.array([c['l'] for c in candles_1h])
        
        if side == 'LONG':
            recent_highs = highs[-50:]
            potential_tp1 = recent_highs[recent_highs > level]
            tp1 = np.min(potential_tp1) if len(potential_tp1) > 0 else level * 1.03
            tp2 = level * 1.06
            tp3 = level * 1.11
        else:
            recent_lows = lows[-50:]
            potential_tp1 = recent_lows[recent_lows < level]
            tp1 = np.max(potential_tp1) if len(potential_tp1) > 0 else level * 0.97
            tp2 = level * 0.94
            tp3 = level * 0.89
        
        return tp1, tp2, tp3
    
    def _calculate_position_size(self, confidence: int) -> str:
        """Определение размера позиции"""
        if confidence >= 90:
            return "до 15-20% депо"
        elif confidence >= 75:
            return "до 10-12% депо"
        else:
            return "до 5-8% депо"
    
    def _analyze_btc(self, btc_candles_1h: List) -> str:
        """Анализ состояния BTC"""
        if not btc_candles_1h or len(btc_candles_1h) < 20:
            return 'neutral'
        
        closes = np.array([c['c'] for c in btc_candles_1h])
        recent = closes[-10:]
        change_pct = (recent[-1] - recent[0]) / recent[0] * 100
        
        if change_pct > 1.5:
            return 'bullish'
        elif change_pct < -1.5:
            return 'bearish'
        else:
            return 'neutral'
    
    def _volume_decreasing_on_bearish(self, candles: List) -> bool:
        """Проверка уменьшения объёмов на красных свечах"""
        if len(candles) < 10:
            return False
        
        red_candles = [c for c in candles[-8:] if c['c'] < c['o']]
        if len(red_candles) < 3:
            return False
        
        return red_candles[-1]['v'] < red_candles[0]['v']
    
    def _volume_decreasing_on_bullish(self, candles: List) -> bool:
        """Проверка уменьшения объёмов на зелёных свечах"""
        if len(candles) < 10:
            return False
        
        green_candles = [c for c in candles[-8:] if c['c'] > c['o']]
        if len(green_candles) < 3:
            return False
        
        return green_candles[-1]['v'] < green_candles[0]['v']
    
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
        # ИСПРАВЛЕНИЕ #4: Требуется больше свечей 4H
        return (
            len(candles_1h) >= 100 and
            len(candles_4h) >= 100 and  # Было 50, стало 100
            len(candles_1d) >= 30
        )

crypto_micky_analyzer = CryptoMickyAnalyzer()
