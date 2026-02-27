
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator

class IntradayTechnicalAnalysis:
    
    @staticmethod
    def calculate_vwap(df: pd.DataFrame) -> float:
        """Calculates Volume Weighted Average Price (VWAP)."""
        try:
            if isinstance(df.index, pd.DatetimeIndex):
                current_date = df.index[-1].date()
                today_df = df[df.index.date == current_date].copy()
            else:
                today_df = df.tail(75).copy() # Fallback to approx 1 day of 5m candles
            
            if today_df.empty: return df['close'].iloc[-1]
            
            check = (today_df['high'] + today_df['low'] + today_df['close']) / 3
            vwap = (check * today_df['volume']).cumsum() / today_df['volume'].cumsum()
            return vwap.iloc[-1]
        except:
            return df['close'].iloc[-1]

    @staticmethod
    def detect_orb(df: pd.DataFrame) -> dict:
        """
        Opening Range Breakout (ORB) Detection.
        Checks if price has broken the High/Low of the first 30 minutes.
        """
        try:
            if not isinstance(df.index, pd.DatetimeIndex): return {}
            
            current_date = df.index[-1].date()
            today_df = df[df.index.date == current_date]
            
            if len(today_df) < 2: return {} # Need at least 2 candles
            
            # Assume 15m candles: First 2 candles = 30 mins
            # Assume 5m candles: First 6 candles = 30 mins
            # We'll take the first 2 rows generically as "Early Range"
            orb_df = today_df.iloc[:2] 
            
            orb_high = orb_df['high'].max()
            orb_low = orb_df['low'].min()
            current_close = today_df.iloc[-1]['close']
            
            status = "Inside"
            if current_close > orb_high: status = "Breakout"
            elif current_close < orb_low: status = "Breakdown"
            
            return {
                "orb_high": orb_high,
                "orb_low": orb_low,
                "status": status,
                "range_size": orb_high - orb_low
            }
        except:
            return {}

    @staticmethod
    def analyze_gap(df: pd.DataFrame) -> dict:
        """
        Analyzes Gap Up/Down from previous day close.
        """
        try:
            if not isinstance(df.index, pd.DatetimeIndex): return {}
            
            # Split into Today and Yesterday
            current_date = df.index[-1].date()
            today_mask = df.index.date == current_date
            today_df = df[today_mask]
            prev_df = df[~today_mask]
            
            if prev_df.empty or today_df.empty: return {}
            
            prev_close = prev_df.iloc[-1]['close']
            today_open = today_df.iloc[0]['open']
            
            gap_pct = ((today_open - prev_close) / prev_close) * 100
            
            gap_type = "None"
            if gap_pct > 1.0: gap_type = "Gap Up"
            elif gap_pct < -1.0: gap_type = "Gap Down"
            
            return {
                "type": gap_type,
                "pct": gap_pct,
                "prev_close": prev_close,
                "today_open": today_open
            }
        except:
            return {}

    @staticmethod
    def calculate_pivots(df: pd.DataFrame) -> dict:
        """
        Calculates Standard Pivot Points using Previous Day's High, Low, Close.
        Expects df to contain at least 2 days of data.
        """
        try:
            if not isinstance(df.index, pd.DatetimeIndex): return {}
            
            # Identify "Yesterday"
            if len(df) > 0:
                current_date = df.index[-1].date()
                prev_data = df[df.index.date < current_date]
            else:
                prev_data = pd.DataFrame()
            
            if prev_data.empty:
                # Fallback: Use full DF stats if no prev day distinction
                high = df['high'].max()
                low = df['low'].min()
                close = df['close'].iloc[-1]
            else:
                # Get last completed day
                last_date = prev_data.index[-1].date()
                last_day_df = prev_data[prev_data.index.date == last_date]
                high = last_day_df['high'].max()
                low = last_day_df['low'].min()
                close = last_day_df['close'].iloc[-1]
                
            pivot = (high + low + close) / 3
            r1 = (2 * pivot) - low
            s1 = (2 * pivot) - high
            r2 = pivot + (high - low)
            s2 = pivot - (high - low)
            r3 = high + 2 * (pivot - low)
            s3 = low - 2 * (high - pivot)
            
            return {
                "P": pivot, "R1": r1, "S1": s1, "R2": r2, "S2": s2, "R3": r3, "S3": s3
            }
        except:
             return {}

    @staticmethod
    def calculate_ladder(df: pd.DataFrame, current_price: float) -> list:
        """
        Generates a price ladder of significant levels (Pivots + Recent High/Low).
        """
        try:
            pivots = IntradayTechnicalAnalysis.calculate_pivots(df)
            levels = []
            
            if pivots:
                levels.append({"price": pivots["R2"], "label": "R2 (Pivot)", "type": "resistance"})
                levels.append({"price": pivots["R1"], "label": "R1 (Pivot)", "type": "resistance"})
                levels.append({"price": pivots["P"], "label": "Daily Pivot", "type": "neutral"})
                levels.append({"price": pivots["S1"], "label": "S1 (Pivot)", "type": "support"})
                levels.append({"price": pivots["S2"], "label": "S2 (Pivot)", "type": "support"})
                
            # Add Recent Intraday High/Low
            today_mask = df.index.date == df.index[-1].date()
            today_df = df[today_mask]
            
            if not today_df.empty:
                day_high = today_df['high'].max()
                day_low = today_df['low'].min()
                if day_high > current_price * 1.001:
                    levels.append({"price": day_high, "label": "Day High", "type": "resistance"})
                if day_low < current_price * 0.999:
                    levels.append({"price": day_low, "label": "Day Low", "type": "support"})
            
            # Use provided levels if any
            return sorted(levels, key=lambda x: x["price"], reverse=True)
        except:
            return []

    @staticmethod
    def analyze_stock(df: pd.DataFrame) -> dict:
        """Institutional-grade Intraday Analysis using specific weighted indicators."""
        if df.empty or len(df) < 20: return {}
        
        latest = df.iloc[-1]
        close = latest['close']
        
        # 1. VWAP (30% weight in engine) - Daily anchor is standard
        vwap = IntradayTechnicalAnalysis.calculate_vwap(df)
        vwap_score = 100 if close > vwap else 0
        vwap_status = "Price > VWAP" if vwap_score == 100 else "Price < VWAP"
        
        # 2. RVOL (Relative Volume - 25% weight in engine) - Length 14
        vol_ma = df['volume'].rolling(14).mean().iloc[-1]
        rvol = latest['volume'] / vol_ma if vol_ma > 0 else 1.0
        rvol_score = 100 if rvol >= 2.0 else min(100, (rvol / 2.0) * 100)
        
        # 3. EMA 9 & 20 (10% weight in engine)
        ema_9 = EMAIndicator(close=df['close'], window=9).ema_indicator().iloc[-1]
        ema_20 = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
        
        ema_score = 0
        ema_status = "Bearish"
        if ema_9 > ema_20 and close > ema_9:
            ema_score = 100
            ema_status = "Strong Bullish (> 9EMA > 20EMA)"
        elif ema_9 > ema_20:
            ema_score = 75
            ema_status = "Bullish Cross"
        elif close > ema_20:
            ema_score = 50
            ema_status = "Holding 20EMA"
            
        # 4. Pivot Points (15% weight in engine) - Daily timeframe
        pivots = IntradayTechnicalAnalysis.calculate_pivots(df)
        pivot_score = 50
        pivot_status = "Between Levels"
        res_1 = pivots.get("R1", close * 1.05)
        sup_1 = pivots.get("S1", close * 0.95)
        
        if close > res_1:
            pivot_score = 100  # Clean Breakout
            pivot_status = "Above R1 Breakout"
        elif close < sup_1:
            pivot_score = 0
            pivot_status = "Below S1 Breakdown"
        elif close > pivots.get("P", 0):
            pivot_score = 75
            pivot_status = "Above Central Pivot"
            
        # 5. Price Action / Order Flow Proxy (20% weight in engine)
        # Replacing Level 2 with candle structure: Strong close near high + volume
        candle_range = latest['high'] - latest['low']
        close_relative = (close - latest['low']) / candle_range if candle_range > 0 else 0.5
        
        # A close in the top 20% of the candle is very aggressive buying
        pa_score = 0
        pa_status = "Weak Close"
        if close_relative > 0.8:
            pa_score = 100 if rvol > 1.2 else 80
            pa_status = "Aggressive Buying (Strong Close)"
        elif close_relative > 0.5:
            pa_score = 50
            pa_status = "Neutral Close"
            
        groups = {
            "VWAP": {"score": vwap_score, "details": [{"text": "VWAP Trend", "type": "positive" if vwap_score > 50 else "negative", "label": "VWAP", "value": vwap_status}]},
            "Volume": {"score": rvol_score, "details": [{"text": "Relative Volume", "type": "positive" if rvol >= 1.5 else "neutral", "label": "RVOL", "value": f"{round(rvol,2)}x"}]},
            "Price Action": {"score": pa_score, "details": [{"text": "Order Flow Proxy", "type": "positive" if pa_score > 50 else "negative", "label": "ACTION", "value": pa_status}]},
            "Trend": {"score": ema_score, "details": [{"text": "9/20 EMA", "type": "positive" if ema_score > 50 else "negative", "label": "EMA", "value": ema_status}]},
            "Risk & Levels": {"score": pivot_score, "details": [{"text": "Pivot Defense", "type": "positive" if pivot_score > 50 else "negative", "label": "PIVOT", "value": pivot_status}]}
        }
        
        atr_val = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
        if pd.isna(atr_val) or atr_val == 0: atr_val = close * 0.015
        
        sl_dist = 1.2 * atr_val
        
        # Dynamic Support/Resistance relative to CURRENT price (Fixes broken Entry/Target flips on Gap-Ups)
        valid_res = [v for k, v in pivots.items() if v > close]
        target = min(valid_res) if valid_res else close + (1.5 * sl_dist)
        
        valid_sup = [v for k, v in pivots.items() if v < close]
        best_sup = max(valid_sup) if valid_sup else close - sl_dist
        
        stop_loss = max(best_sup, close - sl_dist)
        
        # Hard limits (Fix for Penny Stocks where ATR < 0.01)
        # Ensure a minimum 0.5% move for target and 0.4% move for stop loss to prevent overlaps
        min_target_dist = max(1.5 * sl_dist, close * 0.005)
        min_stop_dist = max(sl_dist, close * 0.004)
        
        if target <= close: target = close + min_target_dist
        if stop_loss >= close: stop_loss = close - min_stop_dist
        
        # Absolute safeguard against equal values due to rounding on micro-caps
        if round(target, 2) <= round(close, 2): target = close * 1.01
        if round(stop_loss, 2) >= round(close, 2): stop_loss = close * 0.99
        
        target_reason = "Technical Resistance Area" if valid_res else "ATR Momentum Extension"
        
        # Special Bonus Events (Still mapped for the Engine to view)
        orb = IntradayTechnicalAnalysis.detect_orb(df)
        gap = IntradayTechnicalAnalysis.analyze_gap(df)
        
        ladder = IntradayTechnicalAnalysis.calculate_ladder(df, close)
        
        return {
            "vwap_score": vwap_score,
            "rvol_score": rvol_score,
            "ema_score": ema_score,
            "pivot_score": pivot_score,
            "pa_score": pa_score,
            "vwap_val": vwap,
            "rvol_val": rvol,
            "groups": groups,
            "is_bullish_trend": ema_score >= 50 and vwap_score == 100,
            "trend": "BULLISH" if ema_score > 50 else "BEARISH" if ema_score < 50 else "NEUTRAL",
            "support": round(stop_loss, 2),
            "resistance": round(target, 2),
            "levels": ladder,
            "target_reason": target_reason,
            "atr": atr_val,
            "orb": orb,
            "gap": gap
        }

ta_intraday = IntradayTechnicalAnalysis()
