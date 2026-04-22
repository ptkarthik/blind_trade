import pandas as pd
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
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
    V3: Conviction-Weighted Multi-Strategy with MACD Confluence & Adaptive R:R.
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
        ctx['ema_9'] = EMAIndicator(close=close_series, window=9).ema_indicator()
        ctx['rsi'] = RSIIndicator(close=close_series, window=14).rsi()
        ctx['atr'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
        ctx['adx'] = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14).adx()
        ctx['obv'] = OnBalanceVolumeIndicator(close=df['close'], volume=df['volume']).on_balance_volume()
        ctx['vol_ma'] = vol_s.rolling(20).mean()
        ctx['close_series'] = close_series
        ctx['vol_s'] = vol_s

        # --- V3: MACD Confluence ---
        macd_obj = MACD(close=close_series, window_slow=26, window_fast=12, window_sign=9)
        ctx['macd_line'] = macd_obj.macd()
        ctx['macd_signal'] = macd_obj.macd_signal()
        ctx['macd_hist'] = macd_obj.macd_diff()

        # --- V3: Bollinger Band Squeeze ---
        bb = BollingerBands(close=close_series, window=20, window_dev=2)
        ctx['bb_upper'] = bb.bollinger_hband()
        ctx['bb_lower'] = bb.bollinger_lband()
        ctx['bb_width'] = bb.bollinger_wband()

        # --- V3.2: Multi-Timeframe (MTF) Context ---
        try:
            df_weekly = df.resample('W').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            
            w_close = df_weekly['close']
            if len(w_close) >= 50:
                ctx['w_ema_20'] = EMAIndicator(close=w_close, window=20).ema_indicator()
                ctx['w_sma_50'] = SMAIndicator(close=w_close, window=50).sma_indicator()
                ctx['mtf_enabled'] = True
            else:
                ctx['mtf_enabled'] = False
        except Exception:
            ctx['mtf_enabled'] = False

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
        
        # --- Corporate Action / Gap Risk Filter ---
        gap_pct = ((safe_scalar(latest['open']) - safe_scalar(prev['close'])) / safe_scalar(prev['close'])) * 100
        if gap_pct > 3 or gap_pct < -10:
             return {"match": False, "reason": f"Gap Risk / Corp Action ({round(gap_pct, 1)}%)", "gap_filter_passed": False}
        
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

        # --- V3.2: MTF Weekly Structure Gate ---
        if ctx.get('mtf_enabled'):
            w_ema_20_series = ctx.get('w_ema_20')
            if w_ema_20_series is not None and not w_ema_20_series.dropna().empty:
                w_ema_20 = safe_scalar(w_ema_20_series.dropna().iloc[-1])
                # Reject pullback if Daily close is below the Weekly EMA 20 (Weekly structure broken)
                if w_ema_20 > 0 and close < w_ema_20:
                    return {"match": False, "reason": f"MTF Rejection: Weekly Structure Broken (Close {close} < W-EMA20 {round(w_ema_20,1)})"}

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

        # --- V3.1: TURNAROUND GATE (Anti-Knife-Catching) ---
        # Rule 1: Must be a GREEN candle (close > open) — no buying on red days
        is_green = c_c > c_o
        if not is_green:
            return {"match": False, "reason": "Red Candle — No Turnaround Confirmed"}
        
        # Rule 2: Structural Pivot — today's high must pierce yesterday's high
        prev_high = safe_scalar(prev['high'])
        is_pivot = c_h > prev_high
        if not is_pivot:
            return {"match": False, "reason": f"No Structural Pivot (H:{round(c_h,1)} <= PrevH:{round(prev_high,1)})"}
        
        reasons.append({"text": "Turnaround Confirmed (Green + Pivot)", "type": "positive", "label": "TURNAROUND", "value": "CONFIRMED"})
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
        is_vol_surge = safe_scalar(latest['volume']) > (vol_ma * 1.2)
        is_vol_rising = (vol_s.iloc[-1] > vol_s.iloc[-2] > vol_s.iloc[-3])
        
        if not (is_vol_surge or is_vol_rising):
            return {"match": False, "reason": "No Volume Surge or Rising Trend"}
            
        vol_ratio = safe_scalar(latest['volume']) / max(vol_ma, 1)
        reasons.append({"text": "Volume Health Confirmed", "type": "positive", "label": "VOLUME", "value": f"{round(vol_ratio, 1)}x"})

        # --- V3: MACD Confluence Gate ---
        macd_hist = safe_scalar(ctx['macd_hist'].iloc[-1])
        macd_hist_prev = safe_scalar(ctx['macd_hist'].iloc[-2])
        macd_line = safe_scalar(ctx['macd_line'].iloc[-1])
        macd_signal = safe_scalar(ctx['macd_signal'].iloc[-1])
        
        # Pullback MACD rule: Histogram must be RISING (momentum recovering)
        # OR MACD line must be above signal (still bullish momentum)
        macd_recovering = macd_hist > macd_hist_prev
        macd_bullish = macd_line > macd_signal
        
        if not (macd_recovering or macd_bullish):
            return {"match": False, "reason": f"MACD Not Recovering (Hist: {round(macd_hist, 2)}, Prev: {round(macd_hist_prev, 2)})"}
        
        macd_label = "Recovering" if macd_recovering and not macd_bullish else "Bullish"
        reasons.append({"text": f"MACD: {macd_label}", "type": "positive", "label": "MACD", "value": macd_label})

        # --- V3: OBV Slope Analysis (Institutional Accumulation) ---
        obv_s = ctx['obv']
        obv_current = safe_scalar(obv_s.iloc[-1])
        obv_10d_ago = safe_scalar(obv_s.iloc[-10]) if len(obv_s) >= 10 else obv_current
        obv_rising = obv_current > obv_10d_ago
        # Not a hard gate for pullbacks, but tracked for scoring

        # --- V3: Adaptive ATR Stop & Target ---
        _atr = ctx['atr'].iloc[-1]
        atr = safe_scalar(_atr)
        adx = safe_scalar(ctx['adx'].iloc[-1])
        
        # Adaptive multiplier: Tighter SL in strong trends (ADX>30), wider in weak
        if adx >= 30:
            atr_sl_mult = 1.5   # Strong trend = tight stop
            rr_ratio = 3.0      # Target more aggressive
        elif adx >= 20:
            atr_sl_mult = 2.0   # Normal trend
            rr_ratio = 2.5
        else:
            atr_sl_mult = 2.5   # Choppy = wider stop needed
            rr_ratio = 2.0      # Conservative target
        
        sl = c_c - (atr * atr_sl_mult)
        risk = c_c - sl
        target = c_c + (risk * rr_ratio)
        
        # --- V3: Conviction Score (passed to engine for weighted scoring) ---
        conviction = 0
        if macd_bullish: conviction += 2
        if macd_recovering: conviction += 1
        if obv_rising: conviction += 2
        if vol_ratio > 1.5: conviction += 1
        if adx >= 25: conviction += 1
        if is_pin or is_engulfing: conviction += 2
        if is_inside_break: conviction += 1
        # Range: 0-10
        
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
            "adx": adx,
            "vol_ratio": vol_ratio,
            "conviction": conviction,
            "macd_bullish": macd_bullish,
            "macd_recovering": macd_recovering,
            "obv_rising": obv_rising,
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
        
        # --- Corporate Action / Gap Risk Filter ---
        gap_pct = ((safe_scalar(latest['open']) - safe_scalar(prev['close'])) / safe_scalar(prev['close'])) * 100
        if gap_pct > 3 or gap_pct < -10:
             return {"match": False, "reason": f"Gap Risk / Corp Action ({round(gap_pct, 1)}%)", "gap_filter_passed": False}
             
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

        # --- V3.2: MTF Weekly Structure Gate (Breakout) ---
        if ctx.get('mtf_enabled'):
            w_sma_50_series = ctx.get('w_sma_50')
            if w_sma_50_series is not None and not w_sma_50_series.dropna().empty:
                w_sma_50 = safe_scalar(w_sma_50_series.dropna().iloc[-1])
                # Reject breakout if Daily close is below the Weekly SMA 50
                if w_sma_50 > 0 and c_c < w_sma_50:
                    return {"match": False, "reason": f"MTF Rejection: Counter Weekly Trend (Close {c_c} < W-SMA50 {round(w_sma_50,1)})"}

            
        # --- Volatility Contraction Pattern (VCP) Squeeze Filter ---
        current_range = safe_scalar(latest['high']) - safe_scalar(latest['low'])
        avg_range_10d = (df['high'] - df['low']).iloc[-11:-1].mean()
        
        # The breakout candle MUST be explosive compared to the tight consolidation
        if current_range < (avg_range_10d * 1.3):
             return {"match": False, "reason": f"Missing VCP Squeeze (Range {round(current_range, 1)} < 1.3x Avg {round(avg_range_10d, 1)})", "breakout_strength": "WEAK"}

        # --- V3: Bollinger Band Squeeze Confirmation ---
        bb_width = ctx['bb_width']
        if len(bb_width.dropna()) >= 20:
            current_bw = safe_scalar(bb_width.iloc[-1])
            avg_bw_20 = safe_scalar(bb_width.iloc[-20:].mean())
            # Breakout from a squeeze (current BB width expanding from tight) is highest conviction
            bb_was_squeezed = safe_scalar(bb_width.iloc[-2]) < avg_bw_20
            bb_expanding = current_bw > safe_scalar(bb_width.iloc[-2])
            is_squeeze_breakout = bb_was_squeezed and bb_expanding
        else:
            is_squeeze_breakout = False

        reasons.append({"text": "Bullish Momentum Supported", "type": "positive", "label": "RSI", "value": round(rsi, 1)})

        # 3. Volume Spike (Extremely strict: >2.5x volume required to prevent false breakouts)
        vol_s = ctx['vol_s']
        vol_ma = ctx['vol_ma'].iloc[-1]
        vol_ratio = safe_scalar(latest['volume']) / max(vol_ma, 1)
        
        if vol_ratio < 2.5:
             return {"match": False, "reason": f"Weak Breakout Volume ({round(vol_ratio,1)}x < 2.5x min)"}

        # --- Round 2: ADX Trending Market Check ---
        adx = safe_scalar(ctx['adx'].iloc[-1])
        if adx < 25:
             return {"match": False, "reason": f"Low Trend Momentum (ADX {round(adx,1)} < 25)"}
             
        # --- Round 2: On-Balance Volume (OBV) Accumulation Check ---
        obv_s = ctx['obv']
        obv_rising = False
        if len(obv_s) >= 10:
            obv_current = safe_scalar(obv_s.iloc[-1])
            obv_10d_ago = safe_scalar(obv_s.iloc[-10])
            obv_rising = obv_current > obv_10d_ago
            if not obv_rising:
                 return {"match": False, "reason": "OBV Divergence (Institutional Distribution detected)"}

        reasons.append({"text": "Volume Surge Verified", "type": "positive", "label": "VOLUME", "value": f"{round(vol_ratio, 1)}x"})

        # --- V3: MACD Confluence Gate (Breakout requires MACD above signal) ---
        macd_hist = safe_scalar(ctx['macd_hist'].iloc[-1])
        macd_hist_prev = safe_scalar(ctx['macd_hist'].iloc[-2])
        macd_line = safe_scalar(ctx['macd_line'].iloc[-1])
        macd_signal_val = safe_scalar(ctx['macd_signal'].iloc[-1])
        
        macd_bullish = macd_line > macd_signal_val
        macd_expanding = macd_hist > macd_hist_prev
        
        # Hard gate: Breakout MUST have MACD confirmation
        if not macd_bullish:
            return {"match": False, "reason": f"MACD Bearish (Line {round(macd_line, 2)} < Signal {round(macd_signal_val, 2)})"}
        
        reasons.append({"text": f"MACD Bullish{' (Expanding)' if macd_expanding else ''}", "type": "positive", "label": "MACD", "value": "CONFIRMED"})

        # 4. Candle Strength (Top 30%)
        c_h = safe_scalar(latest['high'])
        c_l = safe_scalar(latest['low'])
        c_range = c_h - c_l
        close_pos = (c_c - c_l) / c_range if c_range > 0 else 1.0
        if close_pos < 0.7:
            return {"match": False, "reason": "Weak Breakout Close (Profit taking in wicks)"}

        # --- V3: Adaptive ATR Stop & Target ---
        atr = safe_scalar(ctx['atr'].iloc[-1])
        
        # Tighter stops in strong trends, wider in weak
        if adx >= 35:
            atr_sl_mult = 1.5   # Very strong trend
            rr_target_1 = 2.5   # Aggressive partial exit
        elif adx >= 25:
            atr_sl_mult = 2.0
            rr_target_1 = 2.0
        else:
            atr_sl_mult = 2.5
            rr_target_1 = 2.0
        
        sl = c_c - (atr * atr_sl_mult)
        risk = c_c - sl
        target_1 = c_c + (risk * rr_target_1)
        
        # --- V3: Conviction Score ---
        conviction = 0
        if macd_bullish: conviction += 2
        if macd_expanding: conviction += 1
        if obv_rising: conviction += 2
        if vol_ratio > 2.0: conviction += 2
        elif vol_ratio > 1.5: conviction += 1
        if adx >= 30: conviction += 1
        if is_squeeze_breakout: conviction += 2
        if close_pos > 0.85: conviction += 1  # Very strong close
        # Range: 0-12
        
        # Determine setup quality
        setup_type = "SQUEEZE_BREAKOUT" if is_squeeze_breakout else "MOMENTUM_BREAKOUT"
        
        return {
            "match": True,
            "strategy": "BREAKOUT",
            "setup_type": setup_type,
            "reasons": reasons,
            "entry": c_c,
            "stop_loss": round(sl, 2),
            "target": round(target_1, 2),
            "risk": round(risk, 2),
            "atr": atr,
            "rsi": rsi,
            "adx": adx,
            "vol_ratio": vol_ratio,
            "conviction": conviction,
            "macd_bullish": macd_bullish,
            "macd_expanding": macd_expanding,
            "obv_rising": obv_rising,
            "is_squeeze_breakout": is_squeeze_breakout,
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
