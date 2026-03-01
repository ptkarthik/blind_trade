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

        # 1. Macro Trend Filter (SMA 50 and SMA 200)
        # Professional standard: Price must be above both 50 and 200 SMAs for high-probability setups.
        sma_50 = SMAIndicator(close=df['close'], window=50).sma_indicator().iloc[-1]
        sma_200 = SMAIndicator(close=df['close'], window=200).sma_indicator().iloc[-1]
        
        is_macro_bullish = (close > sma_50) and (close > sma_200)
        
        if not is_macro_bullish:
            reason = "Below 50 SMA" if close < sma_50 else "Below 200 SMA (No Stage 2 Uptrend)"
            return {"match": False, "reason": f"Fails Macro Trend Logic ({reason})"}
            
        reasons.append({
            "text": "Strong Macro Trend (Above 50/200 SMA)",
            "type": "positive",
            "label": "MACRO",
            "value": f"SMA50: {round(sma_50, 2)}"
        })

        # 2. Support Zones (EMA 20 or SMA 50) - 2.5% Tolerance Bounce (Relaxed from 1.5%)
        ema_20 = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
        
        # Check if price is within +/- 2.5% of either support line
        ema_20_bounce = (ema_20 * 0.975) <= close <= (ema_20 * 1.025)
        sma_50_bounce = (sma_50 * 0.975) <= close <= (sma_50 * 1.025)
        
        is_support_bounce = ema_20_bounce or sma_50_bounce
        
        if not is_support_bounce:
            return {"match": False, "reason": "Not in Support Bounce Zone (2.5% Tolerance)"}
            
        bounce_target = "EMA 20" if ema_20_bounce else "SMA 50"
        bounce_val = ema_20 if ema_20_bounce else sma_50
        reasons.append({
            "text": f"Bouncing off {bounce_target}",
            "type": "positive",
            "label": "SUPPORT",
            "value": f"{bounce_target}: {round(bounce_val, 2)}"
        })

        # 2b. Candlestick Confirmation (Hammer, Pin Bar, or Bullish Engulfing)
        # Check LATEST and PREVIOUS for confirmation (Double window)
        def detect_bullish_pattern(candle, previous):
            body = abs(candle['close'] - candle['open'])
            l_wick = candle['open'] - candle['low'] if candle['close'] > candle['open'] else candle['close'] - candle['low']
            u_wick = candle['high'] - candle['close'] if candle['close'] > candle['open'] else candle['high'] - candle['open']
            
            # Hammer / Pin Bar: Long lower wick (>= 1.5x body), small upper wick
            is_pin = (l_wick >= (1.5 * body)) and (u_wick <= body) and (body >= 0)
            
            # Bullish Engulfing
            is_green = candle['close'] > candle['open']
            prev_red = previous['close'] < previous['open']
            is_engulfing = is_green and prev_red and (candle['open'] <= previous['close']) and (candle['close'] >= previous['open'])
            
            return "Hammer/Pin Bar" if is_pin else "Bullish Engulfing" if is_engulfing else None

        # Check Latest
        pattern = detect_bullish_pattern(latest, prev)
        # Check Previous (Shifted)
        if not pattern and len(df) >= 3:
             pattern = detect_bullish_pattern(prev, df.iloc[-3])
        
        if not pattern:
            return {"match": False, "reason": "No Bullish Candle Confirmation (Hammer/Pin/Engulfing)"}
            
        reasons.append({
            "text": pattern,
            "type": "positive",
            "label": "CANDLE",
            "value": "Confirmed"
        })

        # 3. Momentum Base (RSI 35-65) - Widened from 38-62 based on feedback
        rsi_14 = RSIIndicator(close=df['close'], window=14).rsi().iloc[-1]
        is_rsi_valid = 35 <= rsi_14 <= 65
        
        if not is_rsi_valid:
            return {"match": False, "reason": f"RSI ({round(rsi_14, 1)}) outside 35-65 base"}
            
        reasons.append({
            "text": "RSI building momentum",
            "type": "positive",
            "label": "RSI",
            "value": round(rsi_14, 1)
        })

        # 4. Volume Confirmation (Current Vol > 1.2x 20 Vol MA) - Strict Surge based on feedback
        vol_ma_20 = df['volume'].rolling(20).mean().iloc[-1]
        is_vol_confirmed = latest['volume'] > (vol_ma_20 * 1.2)
        
        if not is_vol_confirmed:
            return {"match": False, "reason": "No Institutional Volume Surge (> 1.2x)"}
            
        vol_ratio = latest['volume'] / vol_ma_20 if vol_ma_20 > 0 else 1
        reasons.append({
            "text": "Volume Surge",
            "type": "positive",
            "label": "VOLUME",
            "value": f"{round(vol_ratio, 2)}x Avg"
        })

        # Phase B & C: Calculate Trading Logistics (Stop, Target, Entry)
        from ta.volatility import AverageTrueRange
        
        # 1. Calculate 14-day ATR for dynamic Stop Loss
        atr_14 = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range().iloc[-1]
        
        # Stop Loss = Entry Price - (Daily ATR value * 1.5)
        stop_loss = close - (atr_14 * 1.5)
        
        # Primary Target (1:2 Risk/Reward)
        risk = close - stop_loss
        target = close + (risk * 2)
        
        # Secondary Target: Recent Swing High (Max high of the last 15 days, shifted back by 1 day to exclude current bounce)
        recent_high = df['high'].shift(1).rolling(15).max().iloc[-1]
        
        # Add a reason for clear UI tracking
        reasons.append({
            "text": "Targets & Stops",
            "type": "neutral",
            "label": "PLAN",
            "value": f"Risk: ₹{round(risk, 2)}"
        })

        return {
            "match": True,
            "reasons": reasons,
            "entry": close,
            "stop_loss": round(stop_loss, 2),
            "target": round(target, 2),
            "secondary_target": round(recent_high, 2) if not np.isnan(recent_high) else None,
            "hold_duration": "2 to 21 Days (Time Stop: 10-14 days sideways)"
        }

ta_swing = SwingTechnicalAnalysis()
