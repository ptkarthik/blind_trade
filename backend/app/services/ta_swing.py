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
    def analyze_pullback(df: pd.DataFrame, nifty_20d_ret: float = 0, ctx: dict = None, earnings_risk: bool = False) -> dict:
        """
        Refined Pullback Strategy: Capturing bounces at supports with flexible confirmation.
        """
        if earnings_risk:
             return {"match": False, "reason": "Binary Earnings Gap Risk (Within 3 days)", "gap_filter_passed": False}
             
        if ctx is None:
            ctx = SwingTechnicalAnalysis.compute_context(df)
        if df.empty or len(df) < 60:
            return {"match": False, "reason": "Insufficient Data"}

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # --- Corporate Action / Gap Risk Filter ---
        gap_pct = ((safe_scalar(latest['open']) - safe_scalar(prev['close'])) / max(safe_scalar(prev['close']), 0.01)) * 100
        # V1.1 Swing Hardening: Raised gap tolerance to 5% for pullbacks (allow strong reversals)
        if gap_pct > 5 or gap_pct < -10:
             return {"match": False, "reason": f"Gap Risk / Corp Action ({round(gap_pct, 1)}%)", "gap_filter_passed": False}
        
        _close = latest['close']
        close = safe_scalar(_close)

        # --- Relative Strength Filter ---
        stock_20d_price = safe_scalar(df['close'].iloc[-21] if len(df) >= 21 else df['close'].iloc[0])
        stock_20d_ret = ((close / stock_20d_price) - 1) * 100 if stock_20d_price > 0 else 0
        
        # V1.1 Swing Hardening: Allowed -5.0% buffer for VCP / base building during index rallies
        if stock_20d_ret <= (nifty_20d_ret - 5.0):
             return {"match": False, "reason": f"Underperforming Nifty ({round(stock_20d_ret, 1)}% vs {round(nifty_20d_ret, 1)}%)", "relative_strength": "UNDERPERFORM"}

        # --- Pullback Quality Constraint (Drawdown < 12%) ---
        recent_high_20d = safe_scalar(df['high'].iloc[-21:-1].max())
        drawdown_pct = ((recent_high_20d - close) / recent_high_20d) * 100 if recent_high_20d > 0 else 0
        
        # [V45] Adaptive drawdown limit: 15% default, 18% if strong trend + relative strength
        adx_check = safe_scalar(ctx['adx'].iloc[-1])
        max_drawdown = 15
        if adx_check > 25 and stock_20d_ret > nifty_20d_ret:
            max_drawdown = 18  # Strong trend + outperforming = allow deeper pullback
        if drawdown_pct > max_drawdown:
             return {"match": False, "reason": f"Deep Correction ({round(drawdown_pct, 1)}% > {max_drawdown}%)", "pullback_quality": "DEEP"}

        # --- V3.2: MTF Weekly Structure Gate (Softened to Conviction Modifier) ---
        mtf_penalty = False
        if ctx.get('mtf_enabled'):
            w_ema_20_series = ctx.get('w_ema_20')
            if w_ema_20_series is not None and not w_ema_20_series.dropna().empty:
                w_ema_20 = safe_scalar(w_ema_20_series.dropna().iloc[-1])
                if w_ema_20 > 0 and close < w_ema_20:
                    # Hard reject only if > 5% below weekly EMA (structural collapse)
                    gap_from_weekly = ((w_ema_20 - close) / w_ema_20) * 100
                    if gap_from_weekly > 5.0:
                        return {"match": False, "reason": f"MTF Rejection: Weekly Structure Broken ({round(gap_from_weekly,1)}% below W-EMA20)"}
                    # 0-5% below: Soft penalty (conviction deduction)
                    mtf_penalty = True

        reasons = []

        # 1. Macro Trend & Slope Filter
        close_series = ctx['close_series']
        _sma_50_series = ctx['sma_50']
        _sma_200_series = ctx['sma_200']
        
        sma_50 = safe_scalar(_sma_50_series.iloc[-1])
        sma_50_prev = safe_scalar(_sma_50_series.iloc[-6]) if len(_sma_50_series) >= 6 else safe_scalar(_sma_50_series.iloc[-2])
        
        # SMA 200 is optional — if data is truncated (< 200 candles), skip the SMA 200 check
        _sma_200_series = ctx['sma_200']
        sma_200 = safe_scalar(_sma_200_series.iloc[-1]) if len(_sma_200_series.dropna()) > 0 else 0.0
        
        # Rule: Price > SMA 50 is hard gate. SMA 200 is bonus confirmation.
        # [V44] SMA 50 slope is now a conviction modifier, not a hard gate
        is_above_sma50 = close > sma_50
        is_above_sma200 = (close > sma_200) if sma_200 > 0 else True  # Skip if unavailable
        is_macro_bullish = is_above_sma50 and is_above_sma200
        is_slope_up = sma_50 > sma_50_prev
        
        if not is_macro_bullish:
            return {"match": False, "reason": f"Fails Trend Filter (Below SMAs)"}
        
        # Slope down = conviction penalty, not hard reject
        slope_penalty = False
        if not is_slope_up:
            slope_penalty = True
            reasons.append({"text": "Caution: SMA 50 Slope Flat/Down", "type": "caution", "label": "TREND", "value": "CAUTIOUS"})
        else:
            reasons.append({"text": "Strong Uptrend (SMA 50 Slope +)", "type": "positive", "label": "TREND", "value": "BULLISH"})

        # 2. Adaptive Support Zones (V1.1: strict pierce and close-hold logic)
        _ema_20 = ctx['ema_20'].iloc[-1]
        ema_20 = safe_scalar(_ema_20)
        
        # [V44] 5-Day Lookback for Support Touch (was 3 — too narrow)
        ema_20_touched = False
        sma_50_touched = False
        lookback = min(5, len(df) - 1)
        if lookback >= 1:
            for i in range(-lookback, 0):
                l_low = safe_scalar(df['low'].iloc[i])
                ema_20_i = safe_scalar(ctx['ema_20'].iloc[i])
                sma_50_i = safe_scalar(ctx['sma_50'].iloc[i])
                if l_low <= (ema_20_i * 1.015): ema_20_touched = True  # [V45] Tightened from 3% to 1.5%
                if l_low <= (sma_50_i * 1.02): sma_50_touched = True  # [V45] Tightened from 3.5% to 2%
        else:
            c_l = safe_scalar(latest['low'])
            ema_20_touched = (c_l <= (ema_20 * 1.015))  # [V45] Tightened from 3% to 1.5%
            sma_50_touched = (c_l <= (sma_50 * 1.02))  # [V45] Tightened from 3.5% to 2%
        
        ema_20_bounce = ema_20_touched and (close >= ema_20)  # [V45] Must close AT or ABOVE support
        sma_50_bounce = sma_50_touched and (close >= sma_50)  # [V45] No more 1% below tolerance
        
        if not (ema_20_bounce or sma_50_bounce):
            return {"match": False, "reason": "Did not touch/hold Support Zone cleanly in last 5 days"}
            
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
            if close_pos < 0.6: # [V45] Not in top 40% (was 50% — too loose for pullback reversals)
                return {"match": False, "reason": f"Weak Close ({round(close_pos*100)}% of range — need top 40%)"}
        
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
        # [V44] Allow pin bars on red candles — long lower wicks ARE valid reversal signals
        is_green = c_c > c_o
        if not is_green and not is_pin:
            return {"match": False, "reason": "Red Candle — No Turnaround Confirmed (no pin bar)"}
        # [V45] Minimum body size for green candles (exclude pin bars which have their own logic)
        if is_green and not is_pin and body_pct < 0.3:
            return {"match": False, "reason": f"Weak Green Candle (body {round(body_pct, 2)}% < 0.3% min)"}
        
        # Rule 2: Structural Pivot — today's high must pierce yesterday's high
        prev_high = safe_scalar(prev['high'])
        is_pivot = c_h > prev_high
        
        turnaround_label = "Turnaround (Green)" if is_green else "Pin Bar Reversal (Red)"
        reasons.append({"text": turnaround_label, "type": "positive", "label": "TURNAROUND", "value": "CONFIRMED"})
        if is_pivot: reasons.append({"text": "Structural Pivot (+)", "type": "positive", "label": "PIVOT", "value": "Yes"})
        reasons.append({"text": f"Patterns: {', '.join(patterns[:2])}", "type": "positive", "label": "CANDLE", "value": "Confirmed"})

        # 4. RSI Setup Mapping (30-70)
        _rsi = ctx['rsi'].iloc[-1]
        rsi = safe_scalar(_rsi)
        # [V44] Raised RSI ceiling from 70 to 75 — strong uptrends often have RSI 70-75
        if not (30 <= rsi <= 75):
            return {"match": False, "reason": f"RSI ({round(rsi,1)}) out of 30-75 range"}
            
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
        # [V45.1] Relative Volume Persistence — institutional accumulation persists for sessions
        vol_3d_avg = safe_scalar(vol_s.iloc[-3:].mean()) / max(vol_ma, 1) if len(vol_s) >= 3 else vol_ratio
        vol_5d_avg = safe_scalar(vol_s.iloc[-5:].mean()) / max(vol_ma, 1) if len(vol_s) >= 5 else vol_ratio
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
        if is_pivot: conviction += 1
        # MTF penalty: deduct 2 points if weekly structure is broken but within tolerance
        if mtf_penalty: conviction -= 2
        # [V44] Slope penalty: deduct 2 points if SMA50 slope is flat/down
        if slope_penalty: conviction -= 2
        # [V44] Red pin bar: deduct 1 point (less confident than green candle)
        if not is_green and is_pin: conviction -= 1
        conviction = max(0, conviction)
        # Range: 0-11
        
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
            "vol_3d_avg": round(vol_3d_avg, 2),
            "vol_5d_avg": round(vol_5d_avg, 2),
            "conviction": conviction,
            "macd_bullish": macd_bullish,
            "macd_recovering": macd_recovering,
            "obv_rising": obv_rising,
            "gap_filter_passed": True,
            "relative_strength": "OUTPERFORM",
            "stock_20d_return": round(stock_20d_ret, 2),
            "pullback_quality": "HEALTHY",
            "drawdown_pct": round(drawdown_pct, 2),
            "consol_days": 0  # Pullbacks don't have a consolidation base
        }

    @staticmethod
    def analyze_breakout(df: pd.DataFrame, nifty_20d_ret: float = 0, ctx: dict = None, earnings_risk: bool = False) -> dict:
        """
        Momentum Breakout Strategy: Capturing clear breaches of 20-day highs in bullish trends.
        """
        if earnings_risk:
             return {"match": False, "reason": "Binary Earnings Gap Risk (Within 3 days)", "gap_filter_passed": False}

        if ctx is None:
            ctx = SwingTechnicalAnalysis.compute_context(df)
        if df.empty or len(df) < 50:
            return {"match": False, "reason": "Insufficient Data"}

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # --- Corporate Action / Gap Risk Filter ---
        gap_pct = ((safe_scalar(latest['open']) - safe_scalar(prev['close'])) / max(safe_scalar(prev['close']), 0.01)) * 100
        # V1.1 Swing Hardening: Raised breakout gap filter from 3% to 8% to catch professional breakaway gaps
        if gap_pct > 8 or gap_pct < -10:
             return {"match": False, "reason": f"Gap Risk / Corp Action ({round(gap_pct, 1)}%)", "gap_filter_passed": False}
             
        c_c = safe_scalar(latest['close'])
        
        # --- Relative Strength Filter ---
        stock_20d_price = safe_scalar(df['close'].iloc[-21] if len(df) >= 21 else df['close'].iloc[0])
        stock_20d_ret = ((c_c / stock_20d_price) - 1) * 100 if stock_20d_price > 0 else 0
        
        # V1.1 Swing Hardening: Allow -5.0% buffer for VCP flat-base breakouts
        if stock_20d_ret <= (nifty_20d_ret - 5.0):
             return {"match": False, "reason": f"Underperforming Nifty ({round(stock_20d_ret, 1)}% vs {round(nifty_20d_ret, 1)}%)", "relative_strength": "UNDERPERFORM"}

        # 1. Price Confirmation: Breakout of 20-day high (3-day lookback)
        is_breakout = False
        high_20_val = 0.0
        if len(df) >= 21:
            # [V45] Check last 2 days only (was 3 — stale breakouts were passing)
            for i in range(-2, 0):
                end_idx = len(df) + i
                start_idx = end_idx - 20
                if start_idx < 0: start_idx = 0
                past_high_20 = safe_scalar(df['high'].iloc[start_idx:end_idx].max())
                past_close = safe_scalar(df['close'].iloc[i])
                if past_close > past_high_20 and c_c > past_high_20:
                    # [V45] Freshness check: current close must be within 2% of breakout day high
                    breakout_day_high = safe_scalar(df['high'].iloc[i])
                    if breakout_day_high > 0 and ((breakout_day_high - c_c) / breakout_day_high) > 0.02:
                        continue  # Stale — price faded from breakout high
                    is_breakout = True
                    high_20_val = past_high_20
                    break
        
        if not is_breakout:
            return {"match": False, "reason": f"Close ({c_c}) did not hold above recent 20D High"}
            
        reasons = [{"text": "Fresh 20-Day Breakout", "type": "positive", "label": "BREAKOUT", "value": "CONFIRMED"}]

        # 2. RSI & Trend
        close_series = ctx['close_series']
        rsi = safe_scalar(ctx['rsi'].iloc[-1])
        
        _sma50_s = ctx['sma_50']
        sma50 = safe_scalar(_sma50_s.iloc[-1])
        sma50_prev = safe_scalar(_sma50_s.iloc[-6]) if len(_sma50_s) >= 6 else safe_scalar(_sma50_s.iloc[-2])
        
        # [V44] RSI lowered from 60 to 55 — many valid breakouts start at RSI 55-60
        if rsi < 55:
            return {"match": False, "reason": f"Insufficient RSI Momentum ({round(rsi,1)} < 55)"}
        
        # [V44] SMA50 slope is now a conviction penalty, not a hard gate
        bo_slope_penalty = False
        if c_c < sma50:
            return {"match": False, "reason": "Below SMA50 — No Breakout"}
        if sma50 <= sma50_prev:
            bo_slope_penalty = True  # Penalize in conviction, don't reject

        # --- [V44] Weekly Macro Trend Proxy (150-Day SMA / 30-Week) --- converted to conviction penalty
        bo_macro_penalty = False
        if len(df) >= 150:
            _sma150_s = ctx['sma_150']
            sma150 = safe_scalar(_sma150_s.iloc[-1])
            if sma150 > 0 and c_c < sma150:
                bo_macro_penalty = True  # Don't hard reject, penalize conviction

        # --- V3.2: MTF Weekly Structure Gate (Softened to Conviction Modifier for Breakout) ---
        bo_mtf_penalty = False
        if ctx.get('mtf_enabled'):
            w_sma_50_series = ctx.get('w_sma_50')
            if w_sma_50_series is not None and not w_sma_50_series.dropna().empty:
                w_sma_50 = safe_scalar(w_sma_50_series.dropna().iloc[-1])
                if w_sma_50 > 0 and c_c < w_sma_50:
                    gap_from_weekly = ((w_sma_50 - c_c) / w_sma_50) * 100
                    if gap_from_weekly > 5.0:
                        return {"match": False, "reason": f"MTF Rejection: Counter Weekly Trend ({round(gap_from_weekly,1)}% below W-SMA50)"}
                    bo_mtf_penalty = True

            
        # --- [V44] Volatility Contraction Pattern (VCP) --- converted from hard gate to conviction bonus
        current_range = safe_scalar(latest['high']) - safe_scalar(latest['low'])
        avg_range_10d = (df['high'] - df['low']).iloc[-11:-1].mean()
        vcp_explosive = current_range >= (avg_range_10d * 1.3)  # Used as conviction bonus below

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

        # --- V45.2: Consolidation Duration (Base Length) ---
        # Count how many days before breakout the stock was in a tight range.
        # Longer consolidation = stronger breakout (more energy stored).
        # A day is "consolidating" if its daily range < 1.5x ATR.
        consol_days = 0
        atr_consol = safe_scalar(ctx['atr'].iloc[-1])
        if atr_consol > 0 and len(df) >= 30:
            for j in range(2, min(61, len(df))):
                day_range = safe_scalar(df['high'].iloc[-j]) - safe_scalar(df['low'].iloc[-j])
                if day_range < (atr_consol * 1.5):
                    consol_days += 1
                else:
                    break  # First wide-range day = consolidation ended

        reasons.append({"text": "Bullish Momentum Supported", "type": "positive", "label": "RSI", "value": round(rsi, 1)})

        # [V44] Volume lowered from 1.8x to 1.5x — large-cap institutional flow is quieter
        vol_s = ctx['vol_s']
        vol_ma = ctx['vol_ma'].iloc[-1]
        vol_ratio = safe_scalar(latest['volume']) / max(vol_ma, 1)
        # [V45.1] Relative Volume Persistence — institutional accumulation persists for sessions
        vol_3d_avg = safe_scalar(vol_s.iloc[-3:].mean()) / max(vol_ma, 1) if len(vol_s) >= 3 else vol_ratio
        vol_5d_avg = safe_scalar(vol_s.iloc[-5:].mean()) / max(vol_ma, 1) if len(vol_s) >= 5 else vol_ratio
        if vol_ratio < 1.5:
             return {"match": False, "reason": f"Weak Breakout Volume ({round(vol_ratio,1)}x < 1.5x min)"}

        # --- Round 2: ADX Trending Market Check ---
        adx = safe_scalar(ctx['adx'].iloc[-1])
        if adx < 20:
             return {"match": False, "reason": f"Low Trend Momentum (ADX {round(adx,1)} < 20)"}
             
        # --- [V44] OBV: conviction modifier instead of hard gate ---
        obv_s = ctx['obv']
        obv_rising = False
        if len(obv_s) >= 10:
            obv_current = safe_scalar(obv_s.iloc[-1])
            obv_10d_ago = safe_scalar(obv_s.iloc[-10])
            obv_rising = obv_current > obv_10d_ago
            # No longer a hard gate — conviction handles it

        reasons.append({"text": "Volume Surge Verified", "type": "positive", "label": "VOLUME", "value": f"{round(vol_ratio, 1)}x"})

        # --- V3: MACD Confluence Gate (Breakout requires MACD above signal) ---
        macd_hist = safe_scalar(ctx['macd_hist'].iloc[-1])
        macd_hist_prev = safe_scalar(ctx['macd_hist'].iloc[-2])
        macd_line = safe_scalar(ctx['macd_line'].iloc[-1])
        macd_signal_val = safe_scalar(ctx['macd_signal'].iloc[-1])
        
        macd_bullish = macd_line > macd_signal_val
        macd_expanding = macd_hist > macd_hist_prev
        
        # [V45] MACD: Conviction penalty instead of hard gate (MACD lags Day-1 breakouts from tight bases)
        bo_macd_penalty = False
        if not macd_bullish:
            bo_macd_penalty = True
            reasons.append({"text": f"MACD Lagging (Penalty -5)", "type": "caution", "label": "MACD", "value": "LAGGING"})
        else:
            reasons.append({"text": f"MACD Bullish{' (Expanding)' if macd_expanding else ''}", "type": "positive", "label": "MACD", "value": "CONFIRMED"})

        # 4. Candle Strength (Top 50%)
        c_h = safe_scalar(latest['high'])
        c_l = safe_scalar(latest['low'])
        c_range = c_h - c_l
        close_pos = (c_c - c_l) / c_range if c_range > 0 else 1.0
        if close_pos < 0.65:  # [V45] Top 35% required (was 50% — letting too many weak closes through)
            return {"match": False, "reason": f"Weak Breakout Close ({round(close_pos*100)}% of range — need top 35%)"}

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
        # [V44] Volume scoring adjusted for new 1.5x floor
        if vol_ratio >= 2.5: conviction += 2
        elif vol_ratio >= 1.8: conviction += 1
        if adx >= 30: conviction += 1
        if is_squeeze_breakout: conviction += 2
        if vcp_explosive: conviction += 1  # [V44] VCP is now a bonus, not a gate
        if close_pos > 0.85: conviction += 1  # Very strong close
        # MTF penalty for breakout
        if bo_mtf_penalty: conviction -= 2
        # [V44] Soft penalties for slope/macro
        if bo_slope_penalty: conviction -= 2
        if bo_macro_penalty: conviction -= 2
        # [V45] MACD lag penalty (Day-1 breakouts from tight bases)
        if bo_macd_penalty: conviction -= 5
        conviction = max(0, conviction)
        # Range: 0-13 (can be reduced by penalties)
        
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
            "vol_3d_avg": round(vol_3d_avg, 2),
            "vol_5d_avg": round(vol_5d_avg, 2),
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
            "volatility_ratio": round(current_range / max(avg_range_10d, 0.1), 2),
            "consol_days": consol_days
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
