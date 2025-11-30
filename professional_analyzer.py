"""
professional_analyzer_v2.py - CryptoMicky Alerts Logic
Полная имплементация ТЗ: анализ уровней, тренда, зон входа, confidence score
"""
import logging
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

class CryptoMickyAnalyzer:
    """
    Анализатор по ТЗ CryptoMicky Alerts
    
    Основные принципы:
    - Анализ уровней поддержки/сопротивления
    - Зонный вход (диапазон цен)
    - Учёт тренда на 4H и 1D
    - Confidence score 0-100%
    - Управление риском по качеству сетапа
    """
    
    def __init__(self):
        # Минимальный порог confidence для выдачи сигнала
        self.min_confidence = 60  # 3/5 условий = 60%
        
        # Условия для LONG (ТЗ п.5.2)
        self.long_conditions = [
            'price_at_support',        # Цена у зоны поддержки
            'support_level_confirmed', # Уровень работал 2+ раза
            'rsi_bullish',            # RSI растёт от 30-45
            'volume_weakness',        # Объёмы на красных уменьшаются
            'btc_neutral_or_up'       # BTC не падает
        ]
        
        # Условия для SHORT (ТЗ п.5.1)
        self.short_conditions = [
            'price_at_resistance',        # Цена у зоны сопротивления
            'resistance_level_confirmed', # Уровень работал 2+ раза
            'rsi_bearish',               # RSI падает от 55-70
            'volume_weakness',           # Объёмы на зелёных уменьшаются
            'btc_neutral_or_down'        # BTC не растёт
        ]
    
    def analyze_pair(self, pair: str, candles_1h: List, candles_4h: List, 
                     candles_1d: List, btc_candles_1h: List = None) -> Optional[Dict]:
        """
        Главный метод анализа пары
        
        Args:
            pair: название пары (ETHUSDT)
            candles_1h: свечи 1H
            candles_4h: свечи 4H  
            candles_1d: свечи 1D
            btc_candles_1h: свечи BTC 1H (опционально)
        
        Returns:
            Dict с сигналом или None
        """
        try:
            # ============ ПРОВЕРКА ДАННЫХ ============
            if not self._validate_data(candles_1h, candles_4h, candles_1d):
                return None
            
            # ============ АНАЛИЗ ТРЕНДА (п.3) ============
            trend_4h = self._determine_trend(candles_4h)
            trend_1d = self._determine_trend(candles_1d)
            
            logger.debug(f"{pair} Trends: 4H={trend_4h}, 1D={trend_1d}")
            
            # Если тренд смешанный → не выдаём сигнал
            if trend_4h == 'mixed' and trend_1d == 'mixed':
                logger.debug(f"{pair}: Mixed trend, no signal")
                return None
            
            # ============ ПОИСК УРОВНЕЙ (п.4) ============
            supports = self._find_support_zones(candles_4h)
            resistances = self._find_resistance_zones(candles_4h)
            
            logger.debug(f"{pair} Levels: {len(supports)} supports, {len(resistances)} resistances")
            
            # ============ АНАЛИЗ BTC ============
            btc_state = self._analyze_btc(btc_candles_1h) if btc_candles_1h else 'neutral'
            
            # ============ АНАЛИЗ LONG (п.5.2) ============
            if trend_4h != 'bearish' or trend_1d != 'bearish':
                long_signal = self._check_long_setup(
                    pair, candles_1h, candles_4h, supports, btc_state
                )
                if long_signal and long_signal['confidence'] >= self.min_confidence:
                    logger.info(f"✅ {pair} LONG signal: {long_signal['confidence']}%")
                    return long_signal
            
            # ============ АНАЛИЗ SHORT (п.5.1) ============
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
    
    # ==================== АНАЛИЗ ТРЕНДА (п.3) ====================
    
    def _determine_trend(self, candles: List) -> str:
        """
        Определение тренда по ТЗ п.3
        
        Тренд определяется минимум по 2 из 4 условий:
        - Структура цены (higher highs / lower lows)
        - RSI выше/ниже 50
        - Цена относительно EMA
        - Объёмы на движениях
        
        Returns:
            'bullish', 'bearish', 'mixed'
        """
        if len(candles) < 50:
            return 'mixed'
        
        closes = np.array([c['c'] for c in candles])
        highs = np.array([c['h'] for c in candles])
        lows = np.array([c['l'] for c in candles])
        volumes = np.array([c['v'] for c in candles])
        
        bull_score = 0
        bear_score = 0
        
        # 1. Структура цены (higher highs / lower lows)
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
        
        # Решение (минимум 2 из 4)
        if bull_score >= 2 and bear_score < 2:
            return 'bullish'
        elif bear_score >= 2 and bull_score < 2:
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
    
    # ==================== ПОИСК УРОВНЕЙ (п.4) ====================
    
    def _find_support_zones(self, candles: List) -> List[Dict]:
        """
        Поиск зон поддержки по ТЗ п.4.2
        
        Уровень = поддержка если:
        - Было минимум 2 отскока
        - На касаниях объёмы покупок росли
        - RSI был в зоне 30-45
        - Расстояние между точками не более 5-10%
        
        Returns:
            List[{'price': 3450.0, 'strength': 3, 'touches': [timestamps]}]
        """
        if len(candles) < 50:
            return []
        
        lows = np.array([c['l'] for c in candles])
        closes = np.array([c['c'] for c in candles])
        volumes = np.array([c['v'] for c in candles])
        
        supports = []
        checked_levels = set()
        
        # Ищем локальные минимумы
        for i in range(10, len(candles)-5):
            current_low = lows[i]
            
            # Пропускаем если уже проверяли похожий уровень
            if any(abs(current_low - checked) / checked < 0.02 for checked in checked_levels):
                continue
            
            # Ищем касания этого уровня
            touches = []
            touch_volumes = []
            
            for j in range(max(0, i-50), min(len(candles), i+50)):
                if j == i:
                    continue
                
                # Проверяем касание (±2%)
                if abs(lows[j] - current_low) / current_low <= 0.02:
                    # Был ли это отскок?
                    if j < len(candles) - 3:
                        next_closes = closes[j+1:j+4]
                        if np.any(next_closes > closes[j] * 1.01):  # Рост >1%
                            touches.append(j)
                            touch_volumes.append(volumes[j])
            
            # Проверяем критерии (минимум 2 касания)
            if len(touches) >= 2:
                # Проверяем объёмы
                avg_volume = np.mean(volumes[max(0, i-20):i])
                high_volume_touches = sum(1 for v in touch_volumes if v > avg_volume)
                
                if high_volume_touches >= 1:
                    supports.append({
                        'price': current_low,
                        'strength': len(touches),
                        'touches': touches,
                        'avg_volume_ratio': np.mean(touch_volumes) / avg_volume
                    })
                    checked_levels.add(current_low)
        
        # Фильтруем только уровни ниже текущей цены
        current_price = closes[-1]
        supports = [s for s in supports if s['price'] < current_price]
        
        # Сортируем по силе
        supports.sort(key=lambda x: (x['strength'], x['avg_volume_ratio']), reverse=True)
        
        return supports[:10]  # Топ 10 уровней
    
    def _find_resistance_zones(self, candles: List) -> List[Dict]:
        """
        Поиск зон сопротивления по ТЗ п.4.1
        
        Уровень = сопротивление если:
        - Было минимум 2 отскока
        - На касаниях объёмы продаж росли
        - RSI был высок (55-70)
        
        Returns:
            List[{'price': 3650.0, 'strength': 3, 'touches': [timestamps]}]
        """
        if len(candles) < 50:
            return []
        
        highs = np.array([c['h'] for c in candles])
        closes = np.array([c['c'] for c in candles])
        volumes = np.array([c['v'] for c in candles])
        
        resistances = []
        checked_levels = set()
        
        # Ищем локальные максимумы
        for i in range(10, len(candles)-5):
            current_high = highs[i]
            
            # Пропускаем если уже проверяли
            if any(abs(current_high - checked) / checked < 0.02 for checked in checked_levels):
                continue
            
            # Ищем касания
            touches = []
            touch_volumes = []
            
            for j in range(max(0, i-50), min(len(candles), i+50)):
                if j == i:
                    continue
                
                # Проверяем касание (±2%)
                if abs(highs[j] - current_high) / current_high <= 0.02:
                    # Был ли это отскок вниз?
                    if j < len(candles) - 3:
                        next_closes = closes[j+1:j+4]
                        if np.any(next_closes < closes[j] * 0.99):  # Падение >1%
                            touches.append(j)
                            touch_volumes.append(volumes[j])
            
            # Проверяем критерии
            if len(touches) >= 2:
                avg_volume = np.mean(volumes[max(0, i-20):i])
                high_volume_touches = sum(1 for v in touch_volumes if v > avg_volume)
                
                if high_volume_touches >= 1:
                    resistances.append({
                        'price': current_high,
                        'strength': len(touches),
                        'touches': touches,
                        'avg_volume_ratio': np.mean(touch_volumes) / avg_volume
                    })
                    checked_levels.add(current_high)
        
        # Фильтруем только уровни выше текущей цены
        current_price = closes[-1]
        resistances = [r for r in resistances if r['price'] > current_price]
        
        # Сортируем по силе
        resistances.sort(key=lambda x: (x['strength'], x['avg_volume_ratio']), reverse=True)
        
        return resistances[:10]
    
    # ==================== ПРОВЕРКА СЕТАПОВ ====================
    
    def _check_long_setup(self, pair: str, candles_1h: List, candles_4h: List,
                          supports: List[Dict], btc_state: str) -> Optional[Dict]:
        """
        Проверка LONG сетапа по ТЗ п.5.2
        
        ВСЕ 5 условий должны быть выполнены:
        1. Цена у зоны поддержки (±1-1.5%)
        2. Уровень работал минимум 2 раза
        3. RSI растёт от 30-45
        4. Объёмы на красных свечах уменьшаются
        5. BTC не падает сильно
        """
        if not supports:
            return None
        
        current_price = candles_1h[-1]['c']
        closes_1h = np.array([c['c'] for c in candles_1h])
        
        # Ищем ближайшую поддержку
        best_support = None
        min_distance = float('inf')
        
        for support in supports:
            distance_pct = abs(current_price - support['price']) / current_price
            if distance_pct <= 0.015 and distance_pct < min_distance:  # 1.5%
                best_support = support
                min_distance = distance_pct
        
        if not best_support:
            return None
        
        # Проверяем ВСЕ 5 условий
        conditions_met = []
        conditions_desc = []
        
        # 1. Цена у поддержки
        distance_pct = abs(current_price - best_support['price']) / current_price * 100
        conditions_met.append('price_at_support')
        conditions_desc.append(f"Цена у поддержки {best_support['price']:.2f}$ (дистанция {distance_pct:.1f}%)")
        
        # 2. Уровень подтверждён (2+ касания)
        if best_support['strength'] >= 2:
            conditions_met.append('support_level_confirmed')
            conditions_desc.append(f"Уровень работал {best_support['strength']} раза")
        else:
            return None  # Критическое условие
        
        # 3. RSI растёт от 30-45
        rsi_1h = self._calculate_rsi(closes_1h)
        rsi_4h = self._calculate_rsi(np.array([c['c'] for c in candles_4h]))
        
        if rsi_1h and rsi_4h:
            if 30 <= rsi_1h <= 48:  # Небольшое расширение диапазона
                if rsi_1h > rsi_4h or closes_1h[-1] > closes_1h[-5]:  # RSI растёт или цена растёт
                    conditions_met.append('rsi_bullish')
                    conditions_desc.append(f"RSI разворачивается вверх ({rsi_1h:.1f})")
        
        # 4. Объёмы на красных свечах уменьшаются
        if self._volume_decreasing_on_bearish(candles_1h):
            conditions_met.append('volume_weakness')
            conditions_desc.append("Объёмы продаж снижаются")
        
        # 5. BTC не падает
        if btc_state in ['neutral', 'bullish']:
            conditions_met.append('btc_neutral_or_up')
            conditions_desc.append(f"BTC {btc_state}")
        
        # Проверяем минимальное количество условий (3/5 = 60%)
        if len(conditions_met) < 3:
            return None
        
        # Создаём сигнал
        return self._create_signal(
            side='LONG',
            pair=pair,
            current_price=current_price,
            level=best_support['price'],
            level_strength=best_support['strength'],
            conditions_met=conditions_met,
            conditions_desc=conditions_desc,
            candles_1h=candles_1h
        )
    
    def _check_short_setup(self, pair: str, candles_1h: List, candles_4h: List,
                           resistances: List[Dict], btc_state: str) -> Optional[Dict]:
        """
        Проверка SHORT сетапа по ТЗ п.5.1
        
        ВСЕ 5 условий должны быть выполнены:
        1. Цена у зоны сопротивления (±1-1.5%)
        2. Уровень работал минимум 2 раза
        3. RSI падает сверху вниз
        4. Объёмы на зелёных свечах уменьшаются
        5. BTC нет бычьего импульса
        """
        if not resistances:
            return None
        
        current_price = candles_1h[-1]['c']
        closes_1h = np.array([c['c'] for c in candles_1h])
        
        # Ищем ближайшее сопротивление
        best_resistance = None
        min_distance = float('inf')
        
        for resistance in resistances:
            distance_pct = abs(current_price - resistance['price']) / current_price
            if distance_pct <= 0.015 and distance_pct < min_distance:
                best_resistance = resistance
                min_distance = distance_pct
        
        if not best_resistance:
            return None
        
        # Проверяем ВСЕ 5 условий
        conditions_met = []
        conditions_desc = []
        
        # 1. Цена у сопротивления
        distance_pct = abs(current_price - best_resistance['price']) / current_price * 100
        conditions_met.append('price_at_resistance')
        conditions_desc.append(f"Цена у сопротивления {best_resistance['price']:.2f}$ (дистанция {distance_pct:.1f}%)")
        
        # 2. Уровень подтверждён
        if best_resistance['strength'] >= 2:
            conditions_met.append('resistance_level_confirmed')
            conditions_desc.append(f"Уровень работал {best_resistance['strength']} раза")
        else:
            return None
        
        # 3. RSI падает сверху
        rsi_1h = self._calculate_rsi(closes_1h)
        rsi_4h = self._calculate_rsi(np.array([c['c'] for c in candles_4h]))
        
        if rsi_1h and rsi_4h:
            if 52 <= rsi_1h <= 72:  # Расширенный диапазон
                if rsi_1h < rsi_4h or closes_1h[-1] < closes_1h[-5]:  # RSI падает или цена падает
                    conditions_met.append('rsi_bearish')
                    conditions_desc.append(f"RSI разворачивается вниз ({rsi_1h:.1f})")
        
        # 4. Объёмы на зелёных свечах уменьшаются
        if self._volume_decreasing_on_bullish(candles_1h):
            conditions_met.append('volume_weakness')
            conditions_desc.append("Объёмы покупок снижаются")
        
        # 5. BTC не растёт
        if btc_state in ['neutral', 'bearish']:
            conditions_met.append('btc_neutral_or_down')
            conditions_desc.append(f"BTC {btc_state}")
        
        # Проверяем минимальное количество условий
        if len(conditions_met) < 3:
            return None
        
        # Создаём сигнал
        return self._create_signal(
            side='SHORT',
            pair=pair,
            current_price=current_price,
            level=best_resistance['price'],
            level_strength=best_resistance['strength'],
            conditions_met=conditions_met,
            conditions_desc=conditions_desc,
            candles_1h=candles_1h
        )
    
    # ==================== СОЗДАНИЕ СИГНАЛА ====================
    
    def _create_signal(self, side: str, pair: str, current_price: float, level: float,
                      level_strength: int, conditions_met: List[str], 
                      conditions_desc: List[str], candles_1h: List) -> Dict:
        """
        Создание финального сигнала по ТЗ п.11
        
        Формат:
        🔻 ETH — SHORT
        Логика: [описание]
        Сценарий:
          Вход: 3450–3470$
          Цели: 3300 → 3180 → 3050$
          Стоп: 3520$
          Объём: до 10–12% депо
          Confidence: 82%
        """
        
        # Confidence Score (ТЗ п.10)
        confidence = self._calculate_confidence(conditions_met, level_strength)
        
        # Зона входа (ТЗ п.6)
        entry_min, entry_max = self._calculate_entry_zone(side, level)
        
        # Стоп-лосс (ТЗ п.7)
        stop_loss = self._calculate_stop_loss(side, level)
        
        # Take Profits (ТЗ п.8)
        tp1, tp2, tp3 = self._calculate_take_profits(side, current_price, level, candles_1h)
        
        # Размер позиции (ТЗ п.9)
        position_size = self._calculate_position_size(confidence)
        
        # Логика
        logic = self._format_logic(side, level, conditions_desc)
        
        return {
            'pair': pair,
            'side': side,
            'current_price': current_price,
            'entry_zone': (entry_min, entry_max),
            'stop_loss': stop_loss,
            'take_profit_1': tp1,
            'take_profit_2': tp2,
            'take_profit_3': tp3,
            'position_size': position_size,
            'confidence': confidence,
            'logic': logic,
            'level': level,
            'conditions_met': len(conditions_met),
            'conditions_total': 5
        }
    
    def _calculate_confidence(self, conditions_met: List[str], level_strength: int) -> int:
        """
        Расчёт Confidence Score по ТЗ п.10
        
        - Каждое условие = +20%
        - Идеальное совпадение (5/5) = +10%
        - Сильный уровень (3+ касания) = +10%
        
        Максимум 100%
        """
        base_score = len(conditions_met) * 20
        
        bonus = 0
        if len(conditions_met) == 5:
            bonus += 10
        if level_strength >= 3:
            bonus += 10
        
        return min(base_score + bonus, 100)
    
    def _calculate_entry_zone(self, side: str, level: float) -> Tuple[float, float]:
        """
        Расчёт зоны входа по ТЗ п.6
        
        LONG: entry_min = level - 0.5%, entry_max = level + 1.5%
        SHORT: entry_min = level - 1.5%, entry_max = level + 0.5%
        """
        if side == 'LONG':
            entry_min = level * 0.995   # -0.5%
            entry_max = level * 1.015   # +1.5%
        else:  # SHORT
            entry_min = level * 0.985   # -1.5%
            entry_max = level * 1.005   # +0.5%
        
        return entry_min, entry_max
    
    def _calculate_stop_loss(self, side: str, level: float) -> float:
        """
        Расчёт стоп-лосса по ТЗ п.7
        
        LONG: stop = level - (1% - 1.5%)
        SHORT: stop = level + (1% - 1.5%)
        """
        if side == 'LONG':
            return level * 0.985  # -1.5%
        else:  # SHORT
            return level * 1.015  # +1.5%
    
    def _calculate_take_profits(self, side: str, current_price: float, 
                                level: float, candles_1h: List) -> Tuple[float, float, float]:
        """
        Расчёт 3 целей по ТЗ п.8
        
        TP1 — ближайшая ликвидность (nearest swing low/high)
        TP2 — среднесрочная зона (следующий уровень ±5-10%)
        TP3 — глубокая цель (сильная зона или 1D уровень)
        """
        closes = np.array([c['c'] for c in candles_1h])
        highs = np.array([c['h'] for c in candles_1h])
        lows = np.array([c['l'] for c in candles_1h])
        
        if side == 'LONG':
            # TP1: ближайший локальный максимум выше уровня
            recent_highs = highs[-50:]
            potential_tp1 = recent_highs[recent_highs > level]
            tp1 = np.min(potential_tp1) if len(potential_tp1) > 0 else level * 1.03
            
            # TP2: ~5-7% выше уровня
            tp2 = level * 1.06
            
            # TP3: ~10-12% выше уровня
            tp3 = level * 1.11
            
        else:  # SHORT
            # TP1: ближайший локальный минимум ниже уровня
            recent_lows = lows[-50:]
            potential_tp1 = recent_lows[recent_lows < level]
            tp1 = np.max(potential_tp1) if len(potential_tp1) > 0 else level * 0.97
            
            # TP2: ~5-7% ниже уровня
            tp2 = level * 0.94
            
            # TP3: ~10-12% ниже уровня
            tp3 = level * 0.89
        
        return tp1, tp2, tp3
    
    def _calculate_position_size(self, confidence: int) -> str:
        """
        Определение размера позиции по ТЗ п.9
        
        Высокое (5/5) → 15-20%
        Среднее (4/5) → 10-12%
        Низкое (3/5) → 5-8%
        """
        if confidence >= 90:
            return "до 15-20% депо"
        elif confidence >= 75:
            return "до 10-12% депо"
        else:
            return "до 5-8% депо"
    
    def _format_logic(self, side: str, level: float, conditions: List[str]) -> str:
        """Форматирование логики для сигнала"""
        zone_type = "поддержки" if side == "LONG" else "сопротивления"
        logic = f"Цена тестирует зону {zone_type} {level:.2f}$"
        
        if conditions:
            details = ", ".join(conditions[:3])  # Первые 3 причины
            logic += f", {details.lower()}"
        
        return logic + "."
    
    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================
    
    def _analyze_btc(self, btc_candles_1h: List) -> str:
        """
        Анализ состояния BTC
        
        Returns:
            'bullish', 'bearish', 'neutral'
        """
        if not btc_candles_1h or len(btc_candles_1h) < 20:
            return 'neutral'
        
        closes = np.array([c['c'] for c in btc_candles_1h])
        
        # Простой анализ: смотрим на последние 10 свечей
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
        
        # Сравниваем первую и последнюю красную свечу
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
        return (
            len(candles_1h) >= 100 and
            len(candles_4h) >= 50 and
            len(candles_1d) >= 30
        )

# Глобальный экземпляр анализатора
crypto_micky_analyzer = CryptoMickyAnalyzer()
