import pandas as pd
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.momentum import RSIIndicator
import numpy as np


def safe_scalar(x):
    import numpy as np
    try:
        if isinstance(x, pd.Series):
             val = float(x.iloc[0]) if len(x) > 0 else 0.0
        elif isinstance(x, pd.DataFrame):
             val = float(x.iloc[0, 0]) if not x.empty else 0.0
        else:
             val = float(x)
        return float(np.nan_to_num(val, nan=0.0))
    except:
        return 0.0

class SwingTechnicalAnalysis:
    """
    Dedicated technical analysis module exclusively for Swing Trading criteria.
    V2: Market-Adaptive Multi-Strategy (Pullback & Breakout).
    """

    @staticmethod
    def compute_context(df: pd.DataFrame) -> dict:
        close_series = df['close'].iloc[:, 0] if isinstance(df['close'], pd.DataFrame) else df['close']
        vol_s = df['volume'].iloc[:, 0] if isinstance(df['volume'], pd.DataFrame) else df['volume']
        from ta.volatility import AverageTrueRange
        from ta.trend import ADXIndicator
        from ta.volume import OnBalanceVolumeIndicator
        
        ctx = {}
        ctx['sma_50'] = SMAIndicator(close=close_series, window=50).sma_indicator()
        ctx['sma_200'] = SMAIndicator(close=close_series, window=200).sma_indicator() if len(df) >= 200 else pd.Series(dtype=float)
        ctx['sma_150'] = SMAIndicator(close=close_series, window=150).sma_indicator() if len(df) >= 150 else pd.Series(dtype=float)
        ctx['ema_20'] = EMAIndicator(close=close_series, window=20).ema_indicator()
        ctx['rsi'] = RSIIndicator(close=close_series, window=14).rsi()
        ctx['atr'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
        ctx['adx'] = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14).adx()
        ctx['obv'] = OnBalanceVolumeIndicator(close=df['close'], volume=df['volume']).on_balance_volume()
        ctx['vol_ma'] = vol_s.rolling(20).mean()
        ctx['close_series'] = close_series
        ctx['vol_s'] = vol_s
        return ctx

    @staticmethod
    def analyze_pullback(df: pd.DataFrame, nifty_20d_ret: float = 0, ctx: dict = None) -> dict:
        """
        Refined Pullback Strategy: Capturing bounces at supports with flexible confirmation.
        """
        if ctx is None:
            ctx = SwingTechnicalAnalysis.compute_context(df)
        if df.empty or len(df) < 60:
            return {"match": False, "reason": "Insufficient Data"}

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # --- Gap Risk Filter ---
        gap_pct = ((safe_scalar(latest['open']) - safe_scalar(prev['close'])) / safe_scalar(prev['close'])) * 100
        if gap_pct > 3 or gap_pct < -2:
             return {"match": False, "reason": f"Gap Risk ({round(gap_pct, 1)}%)", "gap_filter_passed": False}
        
        _close = latest['close']
        close = safe_scalar(_close)

        # --- Relative Strength Filter ---
        stock_20d_price = safe_scalar(df['close'].iloc[-21] if len(df) >= 21 else df['close'].iloc[0])
        stock_20d_ret = ((close / stock_20d_price) - 1) * 100 if stock_20d_price > 0 else 0
        
        if stock_20d_ret <= nifty_20d_ret:
             return {"match": False, "reason": f"Underperforming Nifty ({round(stock_20d_ret, 1)}% vs {round(nifty_20d_ret, 1)}%)", "relative_strength": "UNDERPERFORM"}

        # --- Pullback Quality Constraint (Drawdown < 12%) ---
        recent_high_20d = safe_scalar(df['high'].iloc[-21:-1].max())
        drawdown_pct = ((recent_high_20d - close) / recent_high_20d) * 100 if recent_high_20d > 0 else 0
        
        if drawdown_pct > 12:
             return {"match": False, "reason": f"Deep Correction ({round(drawdown_pct, 1)}% > 12%)", "pullback_quality": "DEEP"}

        reasons = []

        # 1. Macro Trend & Slope Filter
        close_series = ctx['close_series']
        _sma_50_series = ctx['sma_50']
        _sma_200_series = ctx['sma_200']
        
        sma_50 = safe_scalar(_sma_50_series.iloc[-1])
        sma_50_prev = safe_scalar(_sma_50_series.iloc[-2])
        
        # SMA 200 is optional — if data is truncated (< 200 candles), skip the SMA 200 check
        _sma_200_series = ctx['sma_200']
        sma_200 = safe_scalar(_sma_200_series.iloc[-1]) if len(_sma_200_series.dropna()) > 0 else 0.0
        
        # Rule: Price > SMA 50 AND SMA 50 must be trending up (slope > 0)
        # SMA 200 is a bonus confirmation, not a hard gate
        is_above_sma50 = close > sma_50
        is_above_sma200 = (close > sma_200) if sma_200 > 0 else True  # Skip if unavailable
        is_macro_bullish = is_above_sma50 and is_above_sma200
        is_slope_up = sma_50 > sma_50_prev
        
        if not (is_macro_bullish and is_slope_up):
            reason = "Below SMAs" if not is_macro_bullish else "SMA 50 Slope Down"
            return {"match": False, "reason": f"Fails Trend Filter ({reason})"}
            
        reasons.append({"text": "Strong Uptrend (SMA 50 Slope +)", "type": "positive", "label": "TREND", "value": "BULLISH"})

        # 2. Adaptive Support Zones (Wider: EMA20 ±3.5%, SMA50 ±5.0%)
        _ema_20 = ctx['ema_20'].iloc[-1]
        ema_20 = safe_scalar(_ema_20)
        
        ema_20_bounce = (ema_20 * 0.965) <= close <= (ema_20 * 1.035)
        sma_50_bounce = (sma_50 * 0.95) <= close <= (sma_50 * 1.05)
        
        if not (ema_20_bounce or sma_50_bounce):
            return {"match": False, "reason": "Outside Support Zones (EMA20 3.5% / SMA50 5%)"}
            
        bounce_target = "EMA 20" if ema_20_bounce else "SMA 50"
        reasons.append({"text": f"Support Bounce ({bounce_target})", "type": "positive", "label": "ZONE", "value": bounce_target})

        # 3. Market-Adaptive Candle Confirmation
        # Hard Rule: Close must be in top 30% of range
        c_h = safe_scalar(latest['high'])
        c_l = safe_scalar(latest['low'])
        c_o = safe_scalar(latest['open'])
        c_c = close
        
        c_range = c_h - c_l
        if c_range > 0:
            close_pos = (c_c - c_l) / c_range
            if close_pos < 0.7: # Not in top 30%
                return {"match": False, "reason": f"Weak Close ({round(close_pos*100)}% of range)"}
        
        # Pattern Detection
        body = abs(c_c - c_o)
        body_pct = (body / c_o) * 100
        l_wick = min(c_o, c_c) - c_l
        u_wick = c_h - max(c_o, c_c)
        
        is_pin = (l_wick >= (1.5 * body)) and (u_wick <= body)
        is_engulfing = (c_c > c_o) and (safe_scalar(prev['close']) < safe_scalar(prev['open'])) and (c_c >= safe_scalar(prev['open'])) and (c_o <= safe_scalar(prev['close']))
        is_strong_bull = (c_c > c_o) and (body_pct > 1.0)
        
        # Inside Bar Breakout
        is_inside_break = False
        if len(df) >= 3:
            p2 = df.iloc[-2]
            p3 = df.iloc[-3]
            was_inside = (safe_scalar(p2['high']) < safe_scalar(p3['high'])) and (safe_scalar(p2['low']) > safe_scalar(p3['low']))
            is_inside_break = was_inside and (c_c > safe_scalar(p2['high']))
            
        # Higher Low
        is_higher_low = False
        if len(df) >= 3:
            is_higher_low = c_l > safe_scalar(prev['low']) > safe_scalar(df.iloc[-3]['low'])

        patterns = []
        if is_pin: patterns.append("Pin Bar")
        if is_engulfing: patterns.append("Engulfing")
        if is_strong_bull: patterns.append("Strong Bullish (>1%)")
        if is_inside_break: patterns.append("Inside Bar Breakout")
        if is_higher_low: patterns.append("Higher Low")
        
        if not patterns:
            return {"match": False, "reason": "No Bullish Candle Signal"}
            
        reasons.append({"text": f"Patterns: {', '.join(patterns[:2])}", "type": "positive", "label": "CANDLE", "value": "Confirmed"})

        # 4. RSI Setup Mapping (30-70)
        _rsi = ctx['rsi'].iloc[-1]
        rsi = safe_scalar(_rsi)
        if not (30 <= rsi <= 70):
            return {"match": False, "reason": f"RSI ({round(rsi,1)}) out of 30-70 range"}
            
        setup_type = "REVERSAL_PULLBACK" if rsi < 40 else "STANDARD_PULLBACK"
        reasons.append({"text": f"Setup: {setup_type}", "type": "positive", "label": "RSI", "value": round(rsi, 1)})

        # 5. Volume Confirmation (1.2x OR Rising Trend)
        vol_s = ctx['vol_s']
        vol_ma = ctx['vol_ma'].iloc[-1]
        is_vol_surge = c_c > (vol_ma * 1.2)
        is_vol_rising = (vol_s.iloc[-1] > vol_s.iloc[-2] > vol_s.iloc[-3])
        
        if not (is_vol_surge or is_vol_rising):
            return {"match": False, "reason": "No Volume Surge or Rising Trend"}
            
        reasons.append({"text": "Volume Health Confirmed", "type": "positive", "label": "VOLUME", "value": f"{round(safe_scalar(latest['volume'])/vol_ma, 1)}x"})

        # Logistics
        _atr = ctx['atr'].iloc[-1]
        atr = safe_scalar(_atr)
        
        sl = c_c - (atr * 1.5)
        risk = c_c - sl
        target = c_c + (risk * 2)
        
        return {
            "match": True,
            "strategy": "PULLBACK",
            "setup_type": setup_type,
            "reasons": reasons,
            "entry": c_c,
            "stop_loss": round(sl, 2),
            "target": round(target, 2),
            "risk": round(risk, 2),
            "atr": atr,
            "rsi": rsi,
            "vol_ratio": safe_scalar(latest['volume'])/max(vol_ma, 1),
            "gap_filter_passed": True,
            "relative_strength": "OUTPERFORM",
            "stock_20d_return": round(stock_20d_ret, 2),
            "pullback_quality": "HEALTHY",
            "drawdown_pct": round(drawdown_pct, 2)
        }

    @staticmethod
    def analyze_breakout(df: pd.DataFrame, nifty_20d_ret: float = 0, ctx: dict = None) -> dict:
        """
        Momentum Breakout Strategy: Capturing clear breaches of 20-day highs in bullish trends.
        """
        if ctx is None:
            ctx = SwingTechnicalAnalysis.compute_context(df)
        if df.empty or len(df) < 50:
            return {"match": False, "reason": "Insufficient Data"}

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # --- Gap Risk Filter ---
        gap_pct = ((safe_scalar(latest['open']) - safe_scalar(prev['close'])) / safe_scalar(prev['close'])) * 100
        if gap_pct > 3 or gap_pct < -2:
             return {"match": False, "reason": f"Gap Risk ({round(gap_pct, 1)}%)", "gap_filter_passed": False}
             
        c_c = safe_scalar(latest['close'])
        
        # --- Relative Strength Filter ---
        stock_20d_price = safe_scalar(df['close'].iloc[-21] if len(df) >= 21 else df['close'].iloc[0])
        stock_20d_ret = ((c_c / stock_20d_price) - 1) * 100 if stock_20d_price > 0 else 0
        
        if stock_20d_ret <= nifty_20d_ret:
             return {"match": False, "reason": f"Underperforming Nifty ({round(stock_20d_ret, 1)}% vs {round(nifty_20d_ret, 1)}%)", "relative_strength": "UNDERPERFORM"}

        # 1. Price Confirmation: Breakout of 20-day high
        high_20 = safe_scalar(df['high'].iloc[-21:-1].max())
        is_breakout = c_c > high_20
        
        if not is_breakout:
            return {"match": False, "reason": f"Close ({c_c}) below 20D High ({high_20})"}
            
        reasons = [{"text": "Fresh 20-Day Breakout", "type": "positive", "label": "BREAKOUT", "value": "CONFIRMED"}]

        # 2. RSI & Trend
        close_series = ctx['close_series']
        rsi = safe_scalar(ctx['rsi'].iloc[-1])
        
        _sma50_s = ctx['sma_50']
        sma50 = safe_scalar(_sma50_s.iloc[-1])
        sma50_prev = safe_scalar(_sma50_s.iloc[-2])
        
        if rsi < 60:
            return {"match": False, "reason": f"Insufficient RSI Momentum ({round(rsi,1)} < 60)"}
        if c_c < sma50 or sma50 <= sma50_prev:
            return {"match": False, "reason": "Trend not supportive (Below SMA50 or Negative Slope)"}

        # --- Weekly Macro Trend Proxy (150-Day SMA / 30-Week) ---
        if len(df) >= 150:
            _sma150_s = ctx['sma_150']
            sma150 = safe_scalar(_sma150_s.iloc[-1])
            if sma150 > 0 and c_c < sma150:
                return {"match": False, "reason": "Counter Macro-Trend (Below SMA 150 Proxy)"}

            
        # --- Volatility Contraction Pattern (VCP) Squeeze Filter ---
        current_range = safe_scalar(latest['high']) - safe_scalar(latest['low'])
        avg_range_10d = (df['high'] - df['low']).iloc[-11:-1].mean()
        
        # The breakout candle MUST be explosive compared to the tight consolidation
        if current_range < (avg_range_10d * 1.3):
             return {"match": False, "reason": f"Missing VCP Squeeze (Range {round(current_range, 1)} < 1.3x Avg {round(avg_range_10d, 1)})", "breakout_strength": "WEAK"}

        reasons.append({"text": "Bullish Momentum Supported", "type": "positive", "label": "RSI", "value": round(rsi, 1)})

        # 3. Volume Spike
        vol_s = ctx['vol_s']
        vol_ma = ctx['vol_ma'].iloc[-1]
        vol_ratio = safe_scalar(latest['volume']) / max(vol_ma, 1)
        
        if vol_ratio < 1.5:
             return {"match": False, "reason": f"Weak Breakout Volume ({round(vol_ratio,1)}x < 1.5x)"}

        # --- Round 2: ADX Trending Market Check ---
        adx = safe_scalar(ctx['adx'].iloc[-1])
        if adx < 25:
             return {"match": False, "reason": f"Low Trend Momentum (ADX {round(adx,1)} < 25)"}
             
        # --- Round 2: On-Balance Volume (OBV) Accumulation Check ---
        obv_s = ctx['obv']
        if len(obv_s) >= 10:
            obv_current = safe_scalar(obv_s.iloc[-1])
            obv_10d_ago = safe_scalar(obv_s.iloc[-10])
            if obv_current < obv_10d_ago:
                 return {"match": False, "reason": "OBV Divergence (Institutional Distribution detected)"}

        reasons.append({"text": "Volume Surge Verified", "type": "positive", "label": "VOLUME", "value": f"{round(vol_ratio, 1)}x"})

        # 4. Candle Strength (Top 30%)
        c_h = safe_scalar(latest['high'])
        c_l = safe_scalar(latest['low'])
        c_range = c_h - c_l
        close_pos = (c_c - c_l) / c_range if c_range > 0 else 1.0
        if close_pos < 0.7:
            return {"match": False, "reason": "Weak Breakout Close (Profit taking in wicks)"}

        # Logistics
        atr = safe_scalar(ctx['atr'].iloc[-1])
        sl = c_c - (atr * 1.5)
        risk = c_c - sl
        target_1 = c_c + (risk * 1.5) # Initial partial exit
        
        return {
            "match": True,
            "strategy": "BREAKOUT",
            "setup_type": "MOMENTUM_BREAKOUT",
            "reasons": reasons,
            "entry": c_c,
            "stop_loss": round(sl, 2),
            "target": round(target_1, 2),
            "risk": round(risk, 2),
            "atr": atr,
            "rsi": rsi,
            "vol_ratio": vol_ratio,
            "is_hybrid_exit": True,
            "gap_filter_passed": True,
            "relative_strength": "OUTPERFORM",
            "stock_20d_return": round(stock_20d_ret, 2),
            "breakout_strength": "STRONG",
            "volatility_ratio": round(current_range / max(avg_range_10d, 0.1), 2)
        }

    @staticmethod
    def analyze_swing(df: pd.DataFrame) -> dict:
        """
        Backward compatible wrapper for swing engine.
        Returns the best matching strategy based on rules.
        """
        # We will handle conflict resolution in the engine, 
        # but for individual analysis we check both.
        pb = SwingTechnicalAnalysis.analyze_pullback(df)
        bo = SwingTechnicalAnalysis.analyze_breakout(df)
        
        # If both match, we will prefer breakout in strong markets (handled by engine)
        # Default here: prioritize the successful match
        if bo["match"]: return bo
        return pb

ta_swing = SwingTechnicalAnalysis()
