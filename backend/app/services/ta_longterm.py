
import pandas as pd
import numpy as np


def safe_scalar(x):
    import numpy as np
    val = float(x.iloc[0]) if hasattr(x, 'iloc') else float(x)
    return float(np.nan_to_num(val, nan=0.0))
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
from ta.volume import OnBalanceVolumeIndicator

class LongTermTechnicalAnalysis:
    
    @staticmethod
    def calculate_squeeze(df: pd.DataFrame) -> dict:
        """Detects a Volatility Squeeze (Bollinger Bands inside Keltner Channels)."""
        if len(df) < 20: return {"squeeze_on": False, "label": "Normal"}
        _close = df['close']
        close_series = _close.iloc[:, 0] if isinstance(_close, pd.DataFrame) else _close
        sma = close_series.rolling(window=20).mean()
        std = close_series.rolling(window=20).std()
        bb_upper = sma + (2 * std)
        bb_lower = sma - (2 * std)
        
        _high = df['high']
        _low = df['low']
        h_series = _high.iloc[:, 0] if isinstance(_high, pd.DataFrame) else _high
        l_series = _low.iloc[:, 0] if isinstance(_low, pd.DataFrame) else _low
        tr = pd.concat([h_series - l_series, 
                       (h_series - close_series.shift()).abs(), 
                       (l_series - close_series.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(window=20).mean()
        kc_upper = sma + (1.5 * atr)
        kc_lower = sma - (1.5 * atr)
        
        _bb_upper = bb_upper.iloc[-1]
        _kc_upper = kc_upper.iloc[-1]
        _bb_lower = bb_lower.iloc[-1]
        _kc_lower = kc_lower.iloc[-1]
        
        bb_u_val = safe_scalar(_bb_upper)
        kc_u_val = safe_scalar(_kc_upper)
        bb_l_val = safe_scalar(_bb_lower)
        kc_l_val = safe_scalar(_kc_lower)

        squeeze_on = (bb_u_val < kc_u_val) and (bb_l_val > kc_l_val)
        label = "Squeeze On (Coiling)" if squeeze_on else "Normal"
        return {"squeeze_on": squeeze_on, "label": label}

    @staticmethod
    def calculate_drawdown(df: pd.DataFrame) -> dict:
        """Calculates Maximum Drawdown (Risk Control)."""
        if len(df) < 20: return {"max_drawdown_pct": 0, "label": "Unknown"}
        _close = df['close']
        close_series = _close.iloc[:, 0] if isinstance(_close, pd.DataFrame) else _close
        rolling_max = close_series.expanding().max()
        drawdowns = (close_series - rolling_max) / rolling_max
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
            _close = recent_df['close']
            close_series = _close.iloc[:, 0] if isinstance(_close, pd.DataFrame) else _close
            rolling_max = close_series.expanding().max()
            drawdown = (close_series - rolling_max) / rolling_max
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
    def check_trend_template(df: pd.DataFrame) -> dict:
        """
        Mark Minervini's Trend Template (Stage 2 Uptrend).
        Criteria:
        1. Price > 150 SMA and > 200 SMA
        2. 150 SMA > 200 SMA
        3. 200 SMA trending up for at least 1 month (20 days)
        4. 50 SMA > 150 SMA and > 200 SMA
        5. Price > 50 SMA
        6. Price > 52-week low + 25%
        7. Price is within 25% of 52-week high
        """
        try:
            if len(df) < 55: return {"passed": False, "details": "Not enough history"}
            
            _close = df['close']
            close = _close.iloc[:, 0] if isinstance(_close, pd.DataFrame) else _close
            
            # Adjusted for Weekly Data Input (1wk intervals)
            sma_10w = close.rolling(window=10).mean() # Daily 50 equiv
            sma_30w = close.rolling(window=30).mean() # Daily 150 equiv
            sma_40w = close.rolling(window=40).mean() # Daily 200 equiv
            sma_50w = close.rolling(window=50).mean() # True 50-Week SMA
            
            current_close = close.iloc[-1]
            c_50 = sma_10w.iloc[-1]
            c_150 = sma_30w.iloc[-1]
            _c_200 = sma_40w.iloc[-1]
            c_200 = safe_scalar(_c_200)
            _c_50_week = sma_50w.iloc[-1]
            c_50_week = safe_scalar(_c_50_week)
            
            # Check Trend (compare to 4 weeks ago)
            _c_200_prev = sma_40w.iloc[-4]
            c_200_prev = safe_scalar(_c_200_prev)
            trend_200_up = c_200 > c_200_prev
            
            # 52-Week High/Low
            _low = df['low']
            _high = df['high']
            low_series = _low.iloc[:, 0] if isinstance(_low, pd.DataFrame) else _low
            high_series = _high.iloc[:, 0] if isinstance(_high, pd.DataFrame) else _high
            low_52 = low_series.tail(52).min()
            high_52 = high_series.tail(52).max()
            
            abv_low = current_close > (low_52 * 1.25)
            near_high = current_close > (high_52 * 0.75) 
            
            # Condition Checks
            c1 = current_close > c_150 and current_close > c_200
            c2 = c_150 > c_200
            c3 = trend_200_up
            c4 = c_50 > c_150 and c_50 > c_200
            c5 = current_close > c_50
            
            passed = c1 and c2 and c3 and c4 and c5 and abv_low and near_high
            
            reasons = []
            if passed: reasons.append("Stage 2 Uptrend Confirmed")
            elif not c1: reasons.append("Price below L/T MAs")
            elif not c2: reasons.append("150 SMA < 200 SMA")
            elif not c3: reasons.append("200 SMA Flat/Down")
            elif not abv_low: reasons.append("Too close to 52W Low")
            
            return {
                "passed": passed,
                "reason": reasons[0] if reasons else "Mixed Signals",
                "sma_50": c_50,
                "sma_200": c_200,
                "sma_50_week": c_50_week,
                "high_52": high_52
            }
        except:
             return {"passed": False, "reason": "Calculation Error"}

    @staticmethod
    def analyze_volume_behavior(df: pd.DataFrame) -> dict:
        """
        Analyzes Volume Accumulation/Distribution.
        """
        try:
           if len(df) < 50: return {"status": "Neutral", "score": 50}
           
           recent = df.tail(20)
           _open = recent['open']
           _close = recent['close']
           _vol = recent['volume']
           o_s = _open.iloc[:, 0] if isinstance(_open, pd.DataFrame) else _open
           c_s = _close.iloc[:, 0] if isinstance(_close, pd.DataFrame) else _close
           v_s = _vol.iloc[:, 0] if isinstance(_vol, pd.DataFrame) else _vol
           
           up_days = recent[c_s > o_s]
           down_days = recent[c_s < o_s]
           
           up_vol = v_s.loc[up_days.index].mean() if not up_days.empty else 0
           down_vol = v_s.loc[down_days.index].mean() if not down_days.empty else 0
           
           status = "Neutral"
           score = 50
           
           if up_vol > (down_vol * 1.2):
               status = "Accumulation"
               score = 80
           elif down_vol > (up_vol * 1.2):
               status = "Distribution"
               score = 20
           
           # Check for Dry Up on recent pullback (Last 5 days)
           # If price down over last 5 days but volume declining -> Constructive
           last_5 = df.tail(5)
           _l5_c = last_5['close']
           l5_c_s = _l5_c.iloc[:, 0] if isinstance(_l5_c, pd.DataFrame) else _l5_c
           price_drop = l5_c_s.iloc[-1] < l5_c_s.iloc[0]
           
           _l5_v = last_5['volume']
           l5_v_s = _l5_v.iloc[:, 0] if isinstance(_l5_v, pd.DataFrame) else _l5_v
           vol_declining = l5_v_s.iloc[-1] < l5_v_s.mean() * 0.8
           
           dry_up = False
           if price_drop and vol_declining:
               dry_up = True
               status += " (Vol Dry-Up)"
               score += 10
               
           return {"status": status, "score": score, "dry_up": dry_up}
        except:
            return {"status": "Neutral", "score": 50}

    @staticmethod
    def calculate_ladder(df: pd.DataFrame, current_price: float) -> dict:
        """
        Calculates Key Support & Resistance Levels (The 'Ladder').
        Uses 52-Week High, Recent Swing Lows, and Moving Averages.
        """
        try:
            if len(df) < 50: return {"support": current_price * 0.9, "resistance": current_price * 1.1}
            
            # 1. Moving Averages as Dynamic Levels
            _sma_50 = df['close'].rolling(window=50).mean().iloc[-1]
            _sma_200 = df['close'].rolling(window=200).mean().iloc[-1]
            sma_50 = safe_scalar(_sma_50)
            sma_200 = safe_scalar(_sma_200)
            
            # 2. Structural Levels (Swings)
            recent_high = df['high'].tail(60).max()
            recent_low = df['low'].tail(60).min()
            
            # Determine immediate support/resistance
            supports = [l for l in [sma_50, sma_200, recent_low] if l < current_price]
            resistances = [l for l in [sma_50, sma_200, recent_high] if l > current_price]
            
            # Fallbacks
            support = max(supports) if supports else current_price * 0.95
            resistance = min(resistances) if resistances else current_price * 1.05
            
            return {
                "support": round(support, 2),
                "resistance": round(resistance, 2),
                "pivot": round((recent_high + recent_low + current_price) / 3, 2)
            }
        except:
             return {"support": current_price * 0.9, "resistance": current_price * 1.1}

    @staticmethod
    def analyze_stock(df: pd.DataFrame) -> dict:
        """Investor-grade Long-Term Analysis."""
        if df.empty or len(df) < 50: return {}
        latest = df.iloc[-1]
        _close_all = df['close']
        _high_all = df['high']
        _low_all = df['low']
        close_series = _close_all.iloc[:, 0] if isinstance(_close_all, pd.DataFrame) else _close_all
        high_series = _high_all.iloc[:, 0] if isinstance(_high_all, pd.DataFrame) else _high_all
        low_series = _low_all.iloc[:, 0] if isinstance(_low_all, pd.DataFrame) else _low_all
        
        _close_latest = latest['close']
        close = safe_scalar(_close_latest)
        trend_score, mom_score = 0, 0
        groups = {
            "Trend": {"score": 0, "details": [], "status": "NEUTRAL"},
            "Momentum": {"score": 0, "details": [], "status": "NEUTRAL"},
            "Safety": {"score": 0, "details": [], "status": "NEUTRAL"}
        }

        # 1. Trend Analysis (Minervini Template)
        template = LongTermTechnicalAnalysis.check_trend_template(df)
        ema_50 = template.get("sma_50", close)
        ema_200 = template.get("sma_200", close)
        sma_50_week = template.get("sma_50_week", close)
        
        if template["passed"]:
            trend_score = 100
            groups["Trend"]["details"].append({"text": "Minervini Stage 2 Template", "type": "positive", "label": "TREND", "value": "Passed"})
        else:
            # Partial Credit: Guardrail uses the 50-Week SMA for a true long-term hold
            if close > sma_50_week:
                trend_score = 60
                groups["Trend"]["details"].append({"text": "Above 50-Week SMA", "type": "positive", "label": "TREND", "value": "Bullish"})
            else:
                trend_score = 0
                groups["Trend"]["details"].append({"text": "Below 50-Week SMA", "type": "negative", "label": "TREND", "value": "Bearish"})
        
        # 10-Week Pullback Detection (equivalent to 50 DMA)
        dist_to_50 = (close - ema_50) / ema_50
        if 0 < dist_to_50 < 0.03 and trend_score >= 60:
             groups["Trend"]["details"].append({"text": "Pullback to 10-Wk MA (50DMA)", "type": "positive", "label": "SETUP", "value": "Buy Zone"})
             trend_score += 10

        # 2. Volume Analysis
        vol_data = LongTermTechnicalAnalysis.analyze_volume_behavior(df)
        if vol_data["score"] > 60:
             groups["Momentum"]["details"].append({"text": f"Volume: {vol_data['status']}", "type": "positive", "label": "VOL", "value": "Constructive"})
        elif vol_data["score"] < 40:
             groups["Momentum"]["details"].append({"text": f"Volume: {vol_data['status']}", "type": "negative", "label": "VOL", "value": "Weak"})

        # 3. Momentum (RSI)
        _rsi_series = RSIIndicator(close=close_series, window=14).rsi().iloc[-1]
        rsi = safe_scalar(_rsi_series)
        if 40 <= rsi <= 70:
            mom_score = 100
            groups["Momentum"]["details"].append({"text": "RSI Accumulation Zone (40-70)", "type": "positive", "label": "MOM", "value": round(rsi,1)})
        elif rsi > 80:
             groups["Momentum"]["details"].append({"text": "RSI Overbought", "type": "neutral", "label": "MOM", "value": round(rsi,1)})

        dd_data = LongTermTechnicalAnalysis.calculate_drawdown(df)
        recovery_data = LongTermTechnicalAnalysis.calculate_recovery_speed(df)
        
        # Safety Logic
        if dd_data["max_drawdown_pct"] < 15:
             groups["Safety"]["details"].append({"text": "Low Historical Drawdown", "type": "positive", "label": "RISK", "value": f"-{dd_data['max_drawdown_pct']}%"})
        
        # Golden Cross (Bonus)
        # Check if 50 crossed 200 recently? (Already covered by template, but good to explicit)
        
        final_score = (trend_score * 0.5) + (mom_score * 0.3) + (vol_data["score"] * 0.2)
        
        return {
            "score": min(100, round(final_score, 1)), 
            "trend_score": trend_score,
            "mom_score": mom_score,
            "groups": groups,
            "ema_50_val": ema_50,
            "ema_200_val": sma_50_week, # Expose 50-Week SMA to UI
            "rsi": rsi,
            "atr": float((high_series.iloc[-14:] - low_series.iloc[-14:]).mean()),
            "is_bullish_trend": close > sma_50_week,
            "trend": "BULLISH" if trend_score >= 50 else "BEARISH",
            "support": round(ema_50 * 0.98, 2) if trend_score > 60 else round(sma_50_week * 0.95, 2),
            "resistance": round(template.get("high_52", close*1.2), 2),
            "drawdown": dd_data,
            "recovery": recovery_data,
            "levels": LongTermTechnicalAnalysis.calculate_ladder(df, close),
            "squeeze": LongTermTechnicalAnalysis.calculate_squeeze(df),
            "trend_template": template
        }

ta_longterm = LongTermTechnicalAnalysis()
