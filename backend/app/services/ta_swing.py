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
        # Condition: The stock must be in an overall uptrend (trading consistently above its 50 SMA).
        sma_50 = SMAIndicator(close=df['close'], window=50).sma_indicator().iloc[-1]
        is_macro_bullish = close > sma_50
        
        if not is_macro_bullish:
            return {"match": False, "reason": "Fails Macro Uptrend Filter (Below 50 SMA)"}
            
        reasons.append({
            "text": "Above 50 SMA (Uptrend)",
            "type": "positive",
            "label": "MACRO",
            "value": f"SMA: {round(sma_50, 2)}"
        })

        # 2. Support Zones (EMA 20 or SMA 50) - 1.5% Tolerance Bounce
        ema_20 = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
        
        # Check if price is within +/- 1.5% of either support line
        ema_20_bounce = (ema_20 * 0.985) <= close <= (ema_20 * 1.015)
        sma_50_bounce = (sma_50 * 0.985) <= close <= (sma_50 * 1.015)
        
        is_support_bounce = ema_20_bounce or sma_50_bounce
        
        if not is_support_bounce:
            return {"match": False, "reason": "Not in Support Bounce Zone"}
            
        bounce_target = "EMA 20" if ema_20_bounce else "SMA 50"
        bounce_val = ema_20 if ema_20_bounce else sma_50
        reasons.append({
            "text": f"Bouncing off {bounce_target}",
            "type": "positive",
            "label": "SUPPORT",
            "value": f"{bounce_target}: {round(bounce_val, 2)}"
        })

        # 2b. Candlestick Confirmation (Hammer or Bullish Engulfing)
        body_size = abs(latest['close'] - latest['open'])
        lower_wick = latest['open'] - latest['low'] if latest['close'] > latest['open'] else latest['close'] - latest['low']
        upper_wick = latest['high'] - latest['close'] if latest['close'] > latest['open'] else latest['high'] - latest['open']
        
        # Hammer logic: Long lower wick (>= 2x body), small upper wick
        is_hammer = (lower_wick >= (2 * body_size)) and (upper_wick <= body_size) and (body_size > 0)
        
        # Bullish Engulfing: Green candle completely covers previous red candle
        is_green = latest['close'] > latest['open']
        prev_is_red = prev['close'] < prev['open']
        engulfing = is_green and prev_is_red and (latest['open'] <= prev['close']) and (latest['close'] >= prev['open'])
        
        if not (is_hammer or engulfing):
            return {"match": False, "reason": "No Bullish Candlestick Confirmation (Need Hammer or Engulfing)"}
            
        reasons.append({
            "text": "Hammer" if is_hammer else "Bullish Engulfing",
            "type": "positive",
            "label": "CANDLE",
            "value": "Confirmed"
        })

        # 3. Momentum Base (RSI 40-60)
        rsi_14 = RSIIndicator(close=df['close'], window=14).rsi().iloc[-1]
        is_rsi_valid = 40 <= rsi_14 <= 60
        
        if not is_rsi_valid:
            return {"match": False, "reason": f"RSI ({round(rsi_14, 1)}) outside 40-60 base"}
            
        reasons.append({
            "text": "RSI building momentum",
            "type": "positive",
            "label": "RSI",
            "value": round(rsi_14, 1)
        })

        # 4. Volume Confirmation (Current Vol > 20 Vol MA)
        vol_ma_20 = df['volume'].rolling(20).mean().iloc[-1]
        is_vol_confirmed = latest['volume'] > vol_ma_20
        
        if not is_vol_confirmed:
            return {"match": False, "reason": "Fails Volume Surge"}
            
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
