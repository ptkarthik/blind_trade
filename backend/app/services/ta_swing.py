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
        _close = latest['close']
        close = float(_close.iloc[0]) if hasattr(_close, 'iloc') else float(_close)

        reasons = []

        # 1. Macro Trend Filter (SMA 50 and SMA 200)
        # Professional standard: Price must be above both 50 and 200 SMAs for high-probability setups.
        _close = df['close']
        close_series = _close.iloc[:, 0] if isinstance(_close, pd.DataFrame) else _close
        _sma_50 = SMAIndicator(close=close_series, window=50).sma_indicator().iloc[-1]
        _sma_200 = SMAIndicator(close=close_series, window=200).sma_indicator().iloc[-1]
        
        sma_50 = float(_sma_50.iloc[0]) if hasattr(_sma_50, 'iloc') else float(_sma_50)
        sma_200 = float(_sma_200.iloc[0]) if hasattr(_sma_200, 'iloc') else float(_sma_200)
        
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
        _ema_20 = EMAIndicator(close=close_series, window=20).ema_indicator().iloc[-1]
        ema_20 = float(_ema_20.iloc[0]) if hasattr(_ema_20, 'iloc') else float(_ema_20)
        
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
            # Extract scalars safely
            c_c = candle['close']
            c_o = candle['open']
            c_h = candle['high']
            c_l = candle['low']
            p_c = previous['close']
            p_o = previous['open']
            
            c_close = float(c_c.iloc[0]) if hasattr(c_c, 'iloc') else float(c_c)
            c_open = float(c_o.iloc[0]) if hasattr(c_o, 'iloc') else float(c_o)
            c_high = float(c_h.iloc[0]) if hasattr(c_h, 'iloc') else float(c_h)
            c_low = float(c_l.iloc[0]) if hasattr(c_l, 'iloc') else float(c_l)
            
            p_close = float(p_c.iloc[0]) if hasattr(p_c, 'iloc') else float(p_c)
            p_open = float(p_o.iloc[0]) if hasattr(p_o, 'iloc') else float(p_o)
            
            body = abs(c_close - c_open)
            l_wick = c_open - c_low if c_close > c_open else c_close - c_low
            u_wick = c_high - c_close if c_close > c_open else c_high - c_open
            
            # Hammer / Pin Bar: Long lower wick (>= 1.5x body), small upper wick
            is_pin = (l_wick >= (1.5 * body)) and (u_wick <= body) and (body >= 0)
            
            # Bullish Engulfing
            is_green = c_close > c_open
            prev_red = p_close < p_open
            is_engulfing = is_green and prev_red and (c_open <= p_close) and (c_close >= p_open)
            
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
        _rsi_14 = RSIIndicator(close=close_series, window=14).rsi().iloc[-1]
        rsi_14 = float(_rsi_14.iloc[0]) if hasattr(_rsi_14, 'iloc') else float(_rsi_14)
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
        _vol = df['volume']
        vol_series = _vol.iloc[:, 0] if isinstance(_vol, pd.DataFrame) else _vol
        vol_ma_20 = vol_series.rolling(20).mean().iloc[-1]
        _l_vol = latest['volume']
        l_vol_val = float(_l_vol.iloc[0]) if hasattr(_l_vol, 'iloc') else float(_l_vol)
        is_vol_confirmed = l_vol_val > (vol_ma_20 * 1.2)
        
        if not is_vol_confirmed:
            return {"match": False, "reason": "No Institutional Volume Surge (> 1.2x)"}
            
        vol_ratio = l_vol_val / vol_ma_20 if vol_ma_20 > 0 else 1
        reasons.append({
            "text": "Volume Surge",
            "type": "positive",
            "label": "VOLUME",
            "value": f"{round(vol_ratio, 2)}x Avg"
        })

        # Phase B & C: Calculate Trading Logistics (Stop, Target, Entry)
        from ta.volatility import AverageTrueRange
        
        # 1. Calculate 14-day ATR for dynamic Stop Loss
        _high = df['high']
        _low = df['low']
        high_series = _high.iloc[:, 0] if isinstance(_high, pd.DataFrame) else _high
        low_series = _low.iloc[:, 0] if isinstance(_low, pd.DataFrame) else _low
        _atr_14 = AverageTrueRange(high=high_series, low=low_series, close=close_series, window=14).average_true_range().iloc[-1]
        atr_14 = float(_atr_14.iloc[0]) if hasattr(_atr_14, 'iloc') else float(_atr_14)
        
        # Stop Loss = Entry Price - (Daily ATR value * 1.5)
        stop_loss = close - (atr_14 * 1.5)
        
        # Primary Target (1:2 Risk/Reward)
        risk = close - stop_loss
        target = close + (risk * 2)
        
        # Secondary Target: Recent Swing High (Max high of the last 15 days, shifted back by 1 day to exclude current bounce)
        _recent_high = df['high'].shift(1).rolling(15).max().iloc[-1]
        recent_high = float(_recent_high.iloc[0]) if hasattr(_recent_high, 'iloc') else float(_recent_high)
        
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
