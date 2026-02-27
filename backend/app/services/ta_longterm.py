
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
            if len(df) < 260: return {"passed": False, "details": "Not enough history"}
            
            close = df['close']
            
            sma_50 = close.rolling(window=50).mean()
            sma_150 = close.rolling(window=150).mean()
            sma_200 = close.rolling(window=200).mean()
            
            current_close = close.iloc[-1]
            c_50 = sma_50.iloc[-1]
            c_150 = sma_150.iloc[-1]
            c_200 = sma_200.iloc[-1]
            
            # Check 200 SMA Trend (compare to 20 days ago)
            c_200_prev = sma_200.iloc[-20]
            trend_200_up = c_200 > c_200_prev
            
            # 52-Week High/Low
            low_52 = df['low'].tail(260).min()
            high_52 = df['high'].tail(260).max()
            
            abv_low = current_close > (low_52 * 1.25)
            near_high = current_close > (high_52 * 0.75) # Within 25% of high means > 75% of high value
            
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
           up_days = recent[recent['close'] > recent['open']]
           down_days = recent[recent['close'] < recent['open']]
           
           up_vol = up_days['volume'].mean() if not up_days.empty else 0
           down_vol = down_days['volume'].mean() if not down_days.empty else 0
           
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
           price_drop = last_5['close'].iloc[-1] < last_5['close'].iloc[0]
           vol_declining = last_5['volume'].iloc[-1] < last_5['volume'].mean() * 0.8
           
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
            sma_50 = df['close'].rolling(window=50).mean().iloc[-1]
            sma_200 = df['close'].rolling(window=200).mean().iloc[-1]
            
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
        close = latest['close']
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
        
        if template["passed"]:
            trend_score = 100
            groups["Trend"]["details"].append({"text": "Minervini Stage 2 Template", "type": "positive", "label": "TREND", "value": "Passed"})
        else:
            # Partial Credit
            if close > ema_200:
                trend_score = 60
                groups["Trend"]["details"].append({"text": "Above 200 EMA", "type": "positive", "label": "TREND", "value": "Bullish"})
            else:
                trend_score = 0
                groups["Trend"]["details"].append({"text": "Below 200 EMA", "type": "negative", "label": "TREND", "value": "Bearish"})
        
        # 50 DMA Pullback Detection
        # If Price is above 200EMA but within 2-3% of 50EMA (and above it OR slightly below)
        dist_to_50 = (close - ema_50) / ema_50
        if 0 < dist_to_50 < 0.03 and trend_score >= 60:
             groups["Trend"]["details"].append({"text": "Pullback to 50 DMA", "type": "positive", "label": "SETUP", "value": "Buy Zone"})
             trend_score += 10

        # 2. Volume Analysis
        vol_data = LongTermTechnicalAnalysis.analyze_volume_behavior(df)
        if vol_data["score"] > 60:
             groups["Momentum"]["details"].append({"text": f"Volume: {vol_data['status']}", "type": "positive", "label": "VOL", "value": "Constructive"})
        elif vol_data["score"] < 40:
             groups["Momentum"]["details"].append({"text": f"Volume: {vol_data['status']}", "type": "negative", "label": "VOL", "value": "Weak"})

        # 3. Momentum (RSI)
        rsi = RSIIndicator(close=df['close'], window=14).rsi().iloc[-1]
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
            "ema_20": ema_50, 
            "ema_50_val": ema_50,
            "ema_200_val": ema_200,
            "rsi": rsi,
            "atr": (df['high'] - df['low']).rolling(14).mean().iloc[-1],
            "is_bullish_trend": close > ema_200,
            "trend": "BULLISH" if trend_score >= 50 else "BEARISH",
            "support": round(ema_50 * 0.98, 2) if trend_score > 60 else round(ema_200 * 0.95, 2),
            "resistance": round(template.get("high_52", close*1.2), 2),
            "drawdown": dd_data,
            "recovery": recovery_data,
            "levels": LongTermTechnicalAnalysis.calculate_ladder(df, close),
            "squeeze": LongTermTechnicalAnalysis.calculate_squeeze(df),
            "trend_template": template
        }

ta_longterm = LongTermTechnicalAnalysis()
