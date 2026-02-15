
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator

class IntradayTechnicalAnalysis:
    
    @staticmethod
    def calculate_pivots(df: pd.DataFrame) -> dict:
        """Standard Daily/Weekly Pivot Points."""
        if len(df) < 2: return {}
        prev = df.iloc[-2]
        p = (prev['high'] + prev['low'] + prev['close']) / 3
        return {
            "P": p,
            "R1": (2 * p) - prev['low'],
            "S1": (2 * p) - prev['high'],
            "R2": p + (prev['high'] - prev['low']),
            "S2": p - (prev['high'] - prev['low'])
        }

    @staticmethod
    def calculate_ladder(df: pd.DataFrame, current_price: float) -> dict:
        """Calculates a 'Technical Ladder' of support and resistance levels for intraday."""
        pivots = IntradayTechnicalAnalysis.calculate_pivots(df)
        
        potential_resistance = []
        potential_support = []
        
        for k, v in pivots.items():
            if v > current_price: potential_resistance.append({"price": v, "label": k, "type": "Pivot"})
            elif v < current_price: potential_support.append({"price": v, "label": k, "type": "Pivot"})
            
        def get_hits(price_level):
            lookback_df = df.tail(50)
            within_range = ((lookback_df['low'] <= price_level * 1.002) & (lookback_df['high'] >= price_level * 0.998))
            return int(within_range.sum())

        for level in potential_resistance + potential_support:
            level["hits"] = get_hits(level["price"])
            level["strength"] = "Normal" if level["hits"] < 2 else "Solid" if level["hits"] < 5 else "Ironclad"

        potential_resistance.sort(key=lambda x: x["price"])
        potential_support.sort(key=lambda x: x["price"], reverse=True)
        
        return {
            "resistance": potential_resistance[:3],
            "support": potential_support[:3]
        }

    @staticmethod
    def analyze_stock(df: pd.DataFrame) -> dict:
        """Institutional-grade Intraday Analysis (15m/5m context)."""
        if df.empty or len(df) < 50: return {}
        
        latest = df.iloc[-1]
        close = latest['close']
        
        trend_score = 0
        mom_score = 0
        vol_score = 0
        safety_score = 0
        
        groups = {
            "Trend": {"score": 0, "details": [], "status": "NEUTRAL"},
            "Momentum": {"score": 0, "details": [], "status": "NEUTRAL"},
            "Volume": {"score": 0, "details": [], "status": "NEUTRAL"},
            "Risk & Levels": {"score": 0, "details": [], "status": "NEUTRAL"}
        }

        # 1. Trend Direction
        try:
            if isinstance(df.index, pd.DatetimeIndex):
                current_date = df.index[-1].date()
                today_df = df[df.index.date == current_date].copy()
            else:
                today_df = df.tail(25).copy()
            
            if not today_df.empty:
                today_df['tp'] = (today_df['high'] + today_df['low'] + today_df['close']) / 3
                today_df['vwap'] = (today_df['tp'] * today_df['volume']).cumsum() / today_df['volume'].cumsum()
                vwap = today_df.iloc[-1]['vwap']
            else: vwap = close
        except: vwap = close

        ema_9 = EMAIndicator(close=df['close'], window=9).ema_indicator().iloc[-1]
        ema_21 = EMAIndicator(close=df['close'], window=21).ema_indicator().iloc[-1]
        ema_50 = EMAIndicator(close=df['close'], window=50).ema_indicator().iloc[-1]

        price_above_vwap = close > vwap
        ema_cross_up = ema_9 > ema_21
        price_above_50 = close > ema_50

        if price_above_vwap and ema_cross_up and price_above_50:
            trend_score = 100
            groups["Trend"]["details"].append({"text": "Full Bullish Alignment", "type": "positive", "label": "TREND", "value": "Price > VWAP/EMA50"})
        elif not price_above_vwap and not ema_cross_up and not price_above_50:
            trend_score = 0
            groups["Trend"]["details"].append({"text": "Full Bearish Alignment", "type": "negative", "label": "TREND", "value": "Price < VWAP/EMA50"})
        else:
            trend_score = 50
            groups["Trend"]["details"].append({"text": "Mixed Trend Signals", "type": "neutral", "label": "TREND", "value": "Entry Caution"})

        # 2. Momentum
        rsi = RSIIndicator(close=df['close'], window=14).rsi().iloc[-1]
        macd_obj = MACD(close=df['close'])
        macd = macd_obj.macd().iloc[-1]
        macd_signal = macd_obj.macd_signal().iloc[-1]
        
        if 50 <= rsi <= 65:
            mom_score += 50
            groups["Momentum"]["details"].append({"text": "RSI Buy Zone (50-65)", "type": "positive", "label": "MOM", "value": f"RSI: {round(rsi,1)}"})
        elif rsi > 70 or rsi < 30:
            mom_score -= 20
            groups["Momentum"]["details"].append({"text": "Exhaustion Risk", "type": "negative", "label": "MOM", "value": f"RSI: {round(rsi,1)}"})

        if macd > macd_signal:
            mom_score += 50
            groups["Momentum"]["details"].append({"text": "MACD Bullish Cross", "type": "positive", "label": "MACD", "value": "Bullish"})
        else:
            groups["Momentum"]["details"].append({"text": "MACD Bearish Cross", "type": "negative", "label": "MACD", "value": "Bearish"})

        # 3. Volume
        vol_ma = df['volume'].rolling(20).mean().iloc[-1]
        vol_ratio = latest['volume'] / vol_ma if vol_ma > 0 else 1.0
        if vol_ratio > 1.5:
            vol_score = 100
            groups["Volume"]["details"].append({"text": "Volume Surge Detected", "type": "positive", "label": "VOL", "value": f"{round(vol_ratio, 1)}x Avg"})
        else:
            vol_score = 30

        # 4. Risk Control
        pivots = IntradayTechnicalAnalysis.calculate_pivots(df)
        atr_val = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
        sl_dist = 1.2 * atr_val
        
        if trend_score > 50:
            stop_loss = close - sl_dist
            target = close + (sl_dist * 1.5)
            target_reason = "1.5x ATR Target"
        else:
            stop_loss = close + sl_dist
            target = close - (sl_dist * 1.5)
            target_reason = "1.5x ATR Target (Short)"

        res_1 = pivots.get("R1", close * 1.05)
        sup_1 = pivots.get("S1", close * 0.95)
        
        if trend_score > 50 and close > res_1 * 0.995:
             safety_score = 50
             groups["Risk & Levels"]["details"].append({"text": "Near Pivot Resistance", "type": "negative", "label": "LEVEL", "value": f"R1: {round(res_1,1)}"})
        else:
             safety_score = 80
        
        final_score = (trend_score * 0.30) + (min(100, mom_score) * 0.20) + (vol_score * 0.20) + (safety_score * 0.15)
        
        ladder = IntradayTechnicalAnalysis.calculate_ladder(df, close)
        
        return {
            "score": round(final_score, 1),
            "trend_score": trend_score,
            "mom_score": min(100, mom_score),
            "vol_score": vol_score,
            "safety_score": safety_score,
            "groups": groups,
            "ema_20": ema_21, 
            "rsi": rsi,
            "vwap_val": vwap,
            "is_bullish_trend": trend_score > 50,
            "ema_200_val": ema_50,
            "trend": "BULLISH" if trend_score > 50 else "BEARISH" if trend_score < 50 else "NEUTRAL",
            "support": round(stop_loss, 2),
            "resistance": round(target, 2),
            "levels": ladder,
            "target_reason": target_reason,
            "atr": atr_val
        }

ta_intraday = IntradayTechnicalAnalysis()
