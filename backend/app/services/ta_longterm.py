
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
from ta.volume import OnBalanceVolumeIndicator

class LongTermTechnicalAnalysis:
    
    @staticmethod
    def calculate_squeeze(df: pd.DataFrame) -> dict:
        """Detects a Volatility Squeeze (Bollinger Bands inside Keltner Channels)."""
        if len(df) < 20: return {"squeeze_on": False, "label": "Normal"}
        sma = df['close'].rolling(window=20).mean()
        std = df['close'].rolling(window=20).std()
        bb_upper = sma + (2 * std)
        bb_lower = sma - (2 * std)
        
        tr = pd.concat([df['high'] - df['low'], 
                       (df['high'] - df['close'].shift()).abs(), 
                       (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(window=20).mean()
        kc_upper = sma + (1.5 * atr)
        kc_lower = sma - (1.5 * atr)
        
        squeeze_on = (bb_upper.iloc[-1] < kc_upper.iloc[-1]) and (bb_lower.iloc[-1] > kc_lower.iloc[-1])
        label = "Squeeze On (Coiling)" if squeeze_on else "Normal"
        return {"squeeze_on": squeeze_on, "label": label}

    @staticmethod
    def calculate_drawdown(df: pd.DataFrame) -> dict:
        """Calculates Maximum Drawdown (Risk Control)."""
        if len(df) < 20: return {"max_drawdown_pct": 0, "label": "Unknown"}
        rolling_max = df['close'].expanding().max()
        drawdowns = (df['close'] - rolling_max) / rolling_max
        max_dd = drawdowns.min()
        return {
            "max_drawdown_pct": round(abs(max_dd) * 100, 1),
            "label": "Conservative" if abs(max_dd) < 0.2 else "Moderate" if abs(max_dd) < 0.4 else "Aggressive"
        }

    @staticmethod
    def calculate_recovery_speed(df: pd.DataFrame) -> dict:
        """Calculates recovery resilience."""
        if len(df) < 50: return {"recovery_weeks": 0, "label": "Unknown"}
        try:
            recent_df = df.tail(100)
            rolling_max = recent_df['close'].expanding().max()
            drawdown = (recent_df['close'] - rolling_max) / rolling_max
            if drawdown.min() > -0.10: return {"recovery_weeks": 0, "label": "Resilient"}
            trough_idx = drawdown.idxmin()
            recovery_df = recent_df.loc[trough_idx:]
            reclaimed = recovery_df[recovery_df['close'] >= rolling_max.loc[trough_idx]].index
            if not reclaimed.empty:
                weeks = (reclaimed[0] - trough_idx).days // 7
                return {"recovery_weeks": weeks, "label": "Fast" if weeks < 12 else "Moderate"}
            return {"recovery_weeks": None, "label": "Slow"}
        except: return {"recovery_weeks": 0, "label": "Unknown"}

    @staticmethod
    def calculate_pivots(df: pd.DataFrame) -> dict:
        if len(df) < 2: return {}
        prev = df.iloc[-2]
        p = (prev['high'] + prev['low'] + prev['close']) / 3
        return {"P": p, "R1": (2 * p) - prev['low'], "S1": (2 * p) - prev['high']}

    @staticmethod
    def calculate_fibonacci(df: pd.DataFrame) -> dict:
        if len(df) < 52: return {}
        high, low = df['high'].tail(52).max(), df['low'].tail(52).min()
        diff = high - low
        return {"0.618": low + 0.618 * diff, "1.0": high, "0.0": low}

    @staticmethod
    def calculate_ladder(df: pd.DataFrame, current_price: float) -> dict:
        pivots = LongTermTechnicalAnalysis.calculate_pivots(df)
        fibs = LongTermTechnicalAnalysis.calculate_fibonacci(df)
        res, sup = [], []
        for k, v in pivots.items():
            if v > current_price: res.append({"price": v, "label": k})
            else: sup.append({"price": v, "label": k})
        for k, v in fibs.items():
            if v > current_price: res.append({"price": v, "label": f"Fib {k}"})
            else: sup.append({"price": v, "label": f"Fib {k}"})
        return {"resistance": sorted(res, key=lambda x: x["price"])[:3], 
                "support": sorted(sup, key=lambda x: x["price"], reverse=True)[:3]}

    @staticmethod
    def analyze_stock(df: pd.DataFrame) -> dict:
        """Investor-grade Long-Term Analysis."""
        if df.empty or len(df) < 50: return {}
        latest = df.iloc[-1]
        close = latest['close']
        trend_score, mom_score = 0, 0
        groups = {
            "Trend": {"score": 0, "details": [], "status": "NEUTRAL"},
            "Momentum": {"score": 0, "details": [], "status": "NEUTRAL"},
            "Safety": {"score": 0, "details": [], "status": "NEUTRAL"}
        }

        ema_200 = EMAIndicator(close=df['close'], window=200).ema_indicator().iloc[-1]
        ema_50 = EMAIndicator(close=df['close'], window=50).ema_indicator().iloc[-1]
        
        if np.isnan(ema_200): ema_200 = close
        if close > ema_200:
            trend_score = 100
            groups["Trend"]["details"].append({"text": "Above 200 EMA (Long-Term Bullish)", "type": "positive", "label": "L/T", "value": "Strong Trend"})
        
        rsi = RSIIndicator(close=df['close'], window=14).rsi().iloc[-1]
        if 40 <= rsi <= 70:
            mom_score = 100
            groups["Momentum"]["details"].append({"text": "RSI Accumulation Zone (40-70)", "type": "positive", "label": "MOM", "value": round(rsi,1)})
        
        dd_data = LongTermTechnicalAnalysis.calculate_drawdown(df)
        recovery_data = LongTermTechnicalAnalysis.calculate_recovery_speed(df)
        
        return {
            "score": (trend_score * 0.6) + (mom_score * 0.4), # Internal TA Blend
            "trend_score": trend_score,
            "mom_score": mom_score,
            "groups": groups,
            "ema_20": ema_50, # Keep legacy key for compatibility
            "ema_50_val": ema_50,
            "ema_200_val": ema_200,
            "rsi": rsi,
            "atr": (df['high'] - df['low']).rolling(14).mean().iloc[-1],
            "is_bullish_trend": close > ema_200,
            "trend": "BULLISH" if trend_score >= 15 else "BEARISH",
            "support": round(ema_200 * 0.95, 2),
            "resistance": round(close * 1.15, 2),
            "drawdown": dd_data,
            "recovery": recovery_data,
            "levels": LongTermTechnicalAnalysis.calculate_ladder(df, close)
        }

ta_longterm = LongTermTechnicalAnalysis()
