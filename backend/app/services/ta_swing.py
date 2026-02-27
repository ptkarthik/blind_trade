import pandas as pd
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.momentum import RSIIndicator
import numpy as np

class SwingTechnicalAnalysis:
    """
    Dedicated technical analysis module exclusively for Swing Trading criteria.
    Operates on Daily (1D) data frames to identify setup bounces.
    """

    @staticmethod
    def analyze_swing(df: pd.DataFrame) -> dict:
        """
        Executes strict boolean logic across 5 parameters.
        Returns detailed scoring and True/False signals.
        """
        if df.empty or len(df) < 200:
            return {"match": False, "reason": "Insufficient Data (Needs 200 Days)"}

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        close = latest['close']

        reasons = []

        # 1. Macro Trend Filter (SMA 200)
        sma_200 = SMAIndicator(close=df['close'], window=200).sma_indicator().iloc[-1]
        is_macro_bullish = close > sma_200
        
        if not is_macro_bullish:
            return {"match": False, "reason": "Fails Macro SMA 200 Filter"}
            
        reasons.append({
            "text": "Above 200 SMA",
            "type": "positive",
            "label": "MACRO",
            "value": f"SMA: {round(sma_200, 2)}"
        })

        # 2. Support Zones (EMA 20 or SMA 50) - 1% Tolerance Bounce
        ema_20 = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
        sma_50 = SMAIndicator(close=df['close'], window=50).sma_indicator().iloc[-1]
        
        # Check if price is within +/- 1% of either support line
        ema_20_bounce = (ema_20 * 0.99) <= close <= (ema_20 * 1.01)
        sma_50_bounce = (sma_50 * 0.99) <= close <= (sma_50 * 1.01)
        
        is_support_bounce = ema_20_bounce or sma_50_bounce
        
        if not is_support_bounce:
            return {"match": False, "reason": "Not in 1% Tolerance Bounce Zone"}
            
        bounce_target = "EMA 20" if ema_20_bounce else "SMA 50"
        bounce_val = ema_20 if ema_20_bounce else sma_50
        reasons.append({
            "text": f"Bouncing off {bounce_target}",
            "type": "positive",
            "label": "SUPPORT",
            "value": f"{bounce_target}: {round(bounce_val, 2)}"
        })

        # 3. Momentum Base (RSI 40-55)
        rsi_14 = RSIIndicator(close=df['close'], window=14).rsi().iloc[-1]
        is_rsi_valid = 40 <= rsi_14 <= 55
        
        if not is_rsi_valid:
            return {"match": False, "reason": f"RSI ({round(rsi_14, 1)}) outside 40-55 base"}
            
        reasons.append({
            "text": "RSI forming base",
            "type": "positive",
            "label": "RSI",
            "value": round(rsi_14, 1)
        })

        # 4. Volume Confirmation (Current Vol > 20 Vol MA)
        vol_ma_20 = df['volume'].rolling(20).mean().iloc[-1]
        is_vol_confirmed = latest['volume'] > vol_ma_20
        
        if not is_vol_confirmed:
            return {"match": False, "reason": "Fails Volume Breakout"}
            
        vol_ratio = latest['volume'] / vol_ma_20 if vol_ma_20 > 0 else 1
        reasons.append({
            "text": "Volume Confirmation",
            "type": "positive",
            "label": "VOLUME",
            "value": f"{round(vol_ratio, 2)}x Avg"
        })

        # 5. Trend Reversal (MACD)
        macd_obj = MACD(close=df['close'])
        macd_line = macd_obj.macd()
        signal_line = macd_obj.macd_signal()
        macd_hist = macd_obj.macd_diff()
        
        curr_macd = macd_line.iloc[-1]
        curr_signal = signal_line.iloc[-1]
        curr_hist = macd_hist.iloc[-1]
        prev_hist = macd_hist.iloc[-2]
        
        macd_cross_up = curr_macd > curr_signal
        hist_improving = curr_hist > prev_hist
        
        is_macd_valid = macd_cross_up or hist_improving
        
        if not is_macd_valid:
            return {"match": False, "reason": "No MACD Trend Reversal"}
            
        macd_text = "MACD Cross Up" if macd_cross_up else "MACD Hist Improving"
        reasons.append({
            "text": macd_text,
            "type": "positive",
            "label": "MACD",
            "value": "Reversing"
        })

        # Calculate Trading Logistics (Stop, Target, Entry)
        # Entry: Current Price
        # Stop Loss: slightly below the bounce line used
        support_line = ema_20 if ema_20_bounce else sma_50
        stop_loss = support_line * 0.985 # Stop Loss at 1.5% below the support line
        
        # Target: Next local high or simple 1:3 R:R
        risk = close - stop_loss
        target = close + (risk * 3) # Target 3R
        
        return {
            "match": True,
            "reasons": reasons,
            "entry": close,
            "stop_loss": round(stop_loss, 2),
            "target": round(target, 2),
            "hold_duration": "3 to 15 Days"
        }

ta_swing = SwingTechnicalAnalysis()
