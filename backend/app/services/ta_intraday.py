import logging
import pandas as pd
import numpy as np
from ta.volume import MFIIndicator
from ta.trend import ADXIndicator, EMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.momentum import RSIIndicator
from app.services.liquidity_service import liquidity_service

_ta_logger = logging.getLogger("ta_intraday")

def safe_scalar(x):
    import numpy as np
    val = float(x.iloc[0]) if hasattr(x, 'iloc') else float(x)
    return float(np.nan_to_num(val, nan=0.0))

def sigmoid(x):
    return 1 / (1 + np.exp(-x))

class IntradayTechnicalAnalysis:
    
    @staticmethod
    def get_time_adjusted_vol_ma(df: pd.DataFrame, default_ma_series: pd.Series = None) -> float:
        """[GAP #1 FIX] Returns time-of-day benchmark volume if available, preventing morning RVOL distortions."""
        symbol = df.attrs.get("symbol", "")
        if not symbol or len(df) == 0:
            return default_ma_series.iloc[-1] if default_ma_series is not None and not default_ma_series.empty else 0.0
            
        try:
            last_ts = df.index[-1]
            if getattr(last_ts, 'tz', None) is None:
                current_time = (last_ts + pd.Timedelta(hours=5, minutes=30)).strftime("%H:%M")
            else:
                try:
                    current_time = last_ts.tz_convert('Asia/Kolkata').strftime("%H:%M")
                except Exception:
                    current_time = last_ts.strftime("%H:%M")
        except Exception:
            current_time = ""
            
        tod_benchmark = liquidity_service.get_benchmark_vol(symbol, current_time) if current_time else 0
        
        if tod_benchmark > 0:
            return float(tod_benchmark)
        else:
            return default_ma_series.iloc[-1] if default_ma_series is not None and not default_ma_series.empty else 0.0

    @staticmethod
    def calculate_institutional_footprint(persistence: int, volume_ratio: float, mean_fp: float = 0.0, std_fp: float = 1.0) -> float:
        """[V14] Centered Sigmoid Footprint for Institutional Alpha."""
        # raw_footprint combines persistence (time) and volume (intensity)
        raw_footprint = persistence * volume_ratio
        
        # Centering using Z-score logic to prevent mid-range saturation
        # std_fp should be > 0 to avoid division by zero
        safe_std = max(std_fp, 0.001)
        z_score = (raw_footprint - mean_fp) / safe_std
        
        return sigmoid(z_score)
        
    @staticmethod
    def calculate_relative_strength_alpha(stock_rets: pd.Series, index_rets: pd.Series) -> float:
        """[V17] Beta-Adjusted RS Alpha. Stock vs Nifty 50."""
        if stock_rets.empty or index_rets.empty: return 0.0
        
        # Calculate trailing beta (20-period)
        try:
            # Align indices 
            common_idx = stock_rets.index.intersection(index_rets.index)
            if len(common_idx) < 5: return stock_rets.iloc[-1] - index_rets.iloc[-1]
            
            s = stock_rets.loc[common_idx]
            i = index_rets.loc[common_idx]
            
            # Beta = Cov(s, i) / Var(i)
            cov = s.cov(i)
            var = i.var()
            beta = cov / var if var > 0 else 1.0
            
            # Alpha = Stock_Return - (Beta * Index_Return)
            # Use current day cumulative returns for the alpha output
            stock_cum = (1 + s).prod() - 1
            index_cum = (1 + i).prod() - 1
            
            alpha = stock_cum - (beta * index_cum)
            return float(alpha)
        except:
            return float(stock_rets.iloc[-1] - index_rets.iloc[-1])

    @staticmethod
    def indicator_integrity_guard(df: pd.DataFrame, indicators: dict) -> dict:
        """[V13] Phase 1: Core Integrity Guard."""
        required = ['ema20', 'ema50', 'vwap', 'atr']
        missing = [f for f in required if indicators.get(f) is None]
        if missing or df is None or df.empty:
            return {"status": "safe_skip", "reason": f"Missing indicators: {missing}"}
            
        # [V23 FIX] Hardened Intra-Session Gap Detection
        # V22 bug: A single partial-data day (e.g., Yahoo returning 6/25 candles for one date 
        # with a 300-min gap) triggered this for EVERY stock. One bad historical day was
        # killing the entire scan.
        #
        # V23 logic:
        # 1. Only check the MOST RECENT trading day (stale gaps are irrelevant)
        # 2. Use IST-aware date splitting (Yahoo returns UTC timestamps for NSE data)
        # 3. Require SEVERE gaps (>120 min) OR multiple moderate gaps (>60 min)
        #    to distinguish genuine halts from data artifacts
        if hasattr(df.index, 'to_series') and len(df) > 10:
            try:
                idx_series = df.index.to_series()
                
                # Convert to IST for correct date splitting
                # Yahoo timestamps are naive UTC — add 5:30 offset for IST date boundaries
                if idx_series.dt.tz is None:
                    ist_times = idx_series + pd.Timedelta(hours=5, minutes=30)
                else:
                    try:
                        ist_times = idx_series.dt.tz_convert('Asia/Kolkata')
                    except Exception:
                        ist_times = idx_series
                
                # Only check the MOST RECENT trading day (today or last session)
                latest_ist_date = ist_times.iloc[-1].date() if hasattr(ist_times.iloc[-1], 'date') else None
                if latest_ist_date is not None:
                    today_mask = ist_times.apply(lambda x: x.date() if hasattr(x, 'date') else None) == latest_ist_date
                    today_diffs = idx_series[today_mask].diff().dt.total_seconds() / 60.0
                    today_diffs = today_diffs.dropna()
                    
                    if len(today_diffs) > 0:
                        # Genuine trading halt: single gap > 120 min (2 full hours missing)
                        has_severe_gap = today_diffs.max() > 120.0
                        # OR: multiple moderate gaps (3+ gaps > 60 min = systematic data failure)
                        moderate_gap_count = (today_diffs > 60.0).sum()
                        
                        if has_severe_gap or moderate_gap_count >= 3:
                            max_gap = today_diffs.max()
                            return {"status": "safe_skip", 
                                    "reason": f"Severe Data Gaps (Trading Halt) - {max_gap:.0f}min gap on {latest_ist_date}"}
            except Exception:
                pass  # If timezone/index issues, don't block the stock
                
        return {"status": "valid"}

    @staticmethod
    def _ensure_series(data):
        if isinstance(data, pd.DataFrame):
            return data.iloc[:, 0]
        return data
    
    @staticmethod
    def calculate_vwap_series(df: pd.DataFrame) -> pd.Series:
        if df is None or df.empty: return pd.Series(dtype=float)
        # [V18 FIX #9] Prevent in-place mutation of input DataFrame
        df = df.copy()
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        
        try:
            # PIONEER FIX: Robust Groupby Session-Anchored VWAP
            # Works perfectly regardless of TZ failures, cleanly anchoring the cumulative volume/price at the start of each calendar day.
            if isinstance(df.index, pd.DatetimeIndex):
                # We calculate 'tp' (Typical Price)
                tp = (df['high'] + df['low'] + df['close']) / 3.0
                
                # Determine date grouping key safely
                date_str = pd.Series(df.index.date, index=df.index)
                
                # Group by date, apply cumulative pv / cumulative v
                cum_pv = (tp * df['volume']).groupby(date_str, group_keys=False).cumsum()
                cum_v = df['volume'].groupby(date_str, group_keys=False).cumsum()
                
                vwap_calc = cum_pv / cum_v
                return vwap_calc
            else:
                # Ultimate fallback if completely missing datetime index (rare)
                today_df = df.tail(25).copy()
                if today_df.empty: return pd.Series([df['close'].iloc[-1]] * len(df), index=df.index)
                tp = (today_df['high'] + today_df['low'] + today_df['close']) / 3
                vwap_calc = (tp * today_df['volume']).cumsum() / today_df['volume'].cumsum()
                return vwap_calc.reindex(df.index).ffill()
        except Exception:
            # Safe Fallback to current closing price if math fails
            return pd.Series([df['close'].iloc[-1]] * len(df), index=df.index)

    @staticmethod
    def calculate_vwap(df: pd.DataFrame) -> float:
        if df is None or df.empty: return 0.0
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        vwap_s = IntradayTechnicalAnalysis.calculate_vwap_series(df)
        return float(vwap_s.iloc[-1]) if not vwap_s.empty else 0.0

    @staticmethod
    def analyze_vwap_advanced(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            vwap_series = IntradayTechnicalAnalysis.calculate_vwap_series(df)
            # Ensure scalars (handle potential duplicate columns/Series)
            vwap_now = safe_scalar(vwap_series.iloc[-1])
            
            close_now = safe_scalar(df['close'].iloc[-1])
            
            # 1. Slope Calculation (Last 5 candles)
            lookback = 5
            if len(vwap_series) >= lookback:
                vwap_prev = vwap_series.iloc[-lookback]
                vwap_prev = safe_scalar(vwap_prev)
                slope_up = vwap_now > vwap_prev
            else:
                slope_up = False
                
            # 2. Reclaim Detection
            # Price Crossed above VWAP in last 2 candles AND high volume
            reclaim_detected = False
            if len(df) >= 3:
                was_below = df['close'].iloc[-2] < vwap_series.iloc[-2] or df['close'].iloc[-3] < vwap_series.iloc[-3]
                is_above = close_now > vwap_now
                vol_ma = df['volume'].rolling(20).mean().iloc[-1]
                high_vol = df['volume'].iloc[-1] > vol_ma * 1.2
                reclaim_detected = was_below and is_above and high_vol
                
            # 3. Oscillation Detection (Choppiness)
            # Count crosses in last 10 candles
            crosses = 0
            if len(df) >= 10:
                short_df = df.tail(10)
                short_vwap = vwap_series.tail(10)
                for i in range(1, len(short_df)):
                    prev_below = short_df['close'].iloc[i-1] < short_vwap.iloc[i-1]
                    curr_above = short_df['close'].iloc[i] > short_vwap.iloc[i]
                    prev_above = short_df['close'].iloc[i-1] > short_vwap.iloc[i-1]
                    curr_below = short_df['close'].iloc[i] < short_vwap.iloc[i]
                    if (prev_below and curr_above) or (prev_above and curr_below):
                        crosses += 1
            
            is_oscillating = crosses >= 3
            
            return {
                "vwap_val": vwap_now,
                "price_above": close_now > vwap_now,
                "slope_up": slope_up,
                "reclaim": reclaim_detected,
                "oscillating": is_oscillating,
                "cross_count": crosses,
                "is_squeeze": (abs(close_now - vwap_now) / vwap_now < 0.0015) # VWAP Squeeze
            }
        except Exception as e:
            print(f"Error in advanced VWAP: {e}")
            return {"vwap_val": 0, "price_above": False, "slope_up": False, "reclaim": False, "oscillating": False}

    @staticmethod
    def detect_vwap_bullish_pullback(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if len(df) < 20: return {"is_pullback_setup": False}
            
            vwap_series = IntradayTechnicalAnalysis.calculate_vwap_series(df)
            vwap_now = safe_scalar(vwap_series.iloc[-1])
            latest = df.iloc[-1]
            
            # Preceding trend verification: MUST have been trending above VWAP
            was_trending_above = False
            if len(df) >= 5:
                closes_above = sum(1 for i in range(-5, -1) if df['close'].iloc[i] > vwap_series.iloc[i])
                if closes_above >= 3:
                    was_trending_above = True
            
            # 1. Test of VWAP (Liquidity Sweep)
            # Must actually pierce VWAP and reject back above it to flush out retail
            pullback_test = (latest['low'] < vwap_now) and (latest['close'] > vwap_now)
            
            # 2. Bullish Confirmation
            body_size = abs(latest['close'] - latest['open'])
            lower_wick = min(latest['close'], latest['open']) - latest['low']
            candle_range = latest['high'] - latest['low']

            # It is bullish if it's green OR if it has a massive lower wick (hammer rejecting VWAP)
            is_strong_rejection = (lower_wick > body_size * 1.5) and (lower_wick > candle_range * 0.4)
            is_bullish = (latest['close'] > latest['open']) or is_strong_rejection
            
            # 3. High Volume
            _vol_all = df['volume']
            vol_series = _vol_all.iloc[:, 0] if isinstance(_vol_all, pd.DataFrame) else _vol_all
            vol_ma = IntradayTechnicalAnalysis.get_time_adjusted_vol_ma(df, vol_series.rolling(20).mean())
            
            _l_vol = latest['volume']
            l_vol_val = safe_scalar(_l_vol)
            high_vol = l_vol_val > vol_ma
            
            setup_detected = pullback_test and is_bullish and high_vol and was_trending_above
            
            return {
                "is_pullback_setup": setup_detected,
                "vwap_val": vwap_now,
                "volume_ratio": round(latest['volume'] / max(vol_ma, 1e-6), 2)
            }
        except Exception as e:
            print(f"Error in VWAP pullback detection: {e}")
            return {"is_pullback_setup": False}

    @staticmethod
    def detect_orb(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if not isinstance(df.index, pd.DatetimeIndex): return {}
            
            try:
                if df.index.tz is None:
                    df.index = df.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
                else:
                    df.index = df.index.tz_convert('Asia/Kolkata')
            except:
                pass
                
            current_date = df.index[-1].date()
            today_df = df[df.index.date == current_date]
            
            if len(today_df) < 2: return {} 
            
            # ORB strictly 09:15:00 to 09:45:00
            start_time = pd.Timestamp.combine(current_date, pd.to_datetime('09:15:00').time())
            end_time = pd.Timestamp.combine(current_date, pd.to_datetime('09:45:00').time())
            if today_df.index.tz is not None:
                start_time = start_time.tz_localize('Asia/Kolkata')
                end_time = end_time.tz_localize('Asia/Kolkata')
                
            orb_df = today_df[(today_df.index >= start_time) & (today_df.index <= end_time)]
            
            if orb_df.empty: return {} 
            
            orb_high = orb_df['high'].max()
            orb_low = orb_df['low'].min()
            
            latest_candle_time = today_df.index[-1]
            current_close = today_df['close'].iloc[-1]
            
            status = "Inside"
            # FIX #7: ORB Early Detection Mode
            # OLD: Signals only valid AFTER 09:45, completely missing the opening surge
            # NEW: Allow early signals if volume is institutional (>250% of avg)
            vol_ma_orb = today_df['volume'].iloc[:-1].mean() if len(today_df) > 1 else 0
            current_vol = today_df['volume'].iloc[-1]
            is_institutional_open = float(current_vol) > float(vol_ma_orb) * 2.5 if vol_ma_orb > 0 else False

            if latest_candle_time > end_time:
                # Standard ORB confirmation (post 09:45)
                if current_close > orb_high: status = "Breakout"
                elif current_close < orb_low: status = "Breakdown"
            elif is_institutional_open:
                # Early ORB detection during the opening range itself
                if current_close > orb_high: status = "Early Breakout"
                elif current_close < orb_low: status = "Early Breakdown"
            
            return {
                "orb_high": orb_high,
                "orb_low": orb_low,
                "status": status,
                "range_size": orb_high - orb_low,
                "early_detection": is_institutional_open
            }
        except Exception as _e:
            _ta_logger.warning(f"[detect_orb] {df.attrs.get('symbol','?')}: {_e}")
            return {}

    @staticmethod
    def analyze_gap(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if not isinstance(df.index, pd.DatetimeIndex): return {}
            
            # Split into Today and Yesterday
            current_date = df.index[-1].date()
            today_mask = df.index.date == current_date
            today_df = df[today_mask]
            prev_df = df[~today_mask]
            
            if prev_df.empty or today_df.empty: return {}
            
            prev_close = prev_df['close'].iloc[-1]
            today_open = today_df.iloc[0]['open']
            current_price = today_df['close'].iloc[-1]
            
            gap_pct = ((today_open - prev_close) / prev_close) * 100
            
            # Fading: Current price is lower than the opening price of the gap
            is_fading = current_price < today_open
            
            # Volume at open relative to average
            # Use the volume of the FIRST candle of today
            opening_vol = today_df.iloc[0]['volume']
            vol_ma = df['volume'].rolling(20).mean().iloc[len(prev_df)] # MA at the time of open
            vol_ratio = opening_vol / max(vol_ma, 1e-6)
            
            gap_type = "None"
            if gap_pct > 1.0: gap_type = "Gap Up"
            elif gap_pct < -1.0: gap_type = "Gap Down"
            
            return {
                "type": gap_type,
                "pct": round(gap_pct, 2),
                "is_fading": is_fading,
                "vol_ratio": round(vol_ratio, 2),
                "prev_close": prev_close,
                "today_open": today_open
            }
        except Exception as _e:
            _ta_logger.warning(f"[analyze_gap] {df.attrs.get('symbol','?')}: {_e}")
            return {"type": "None", "pct": 0, "is_fading": False, "vol_ratio": 0}

    @staticmethod
    def calculate_pivots(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
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
        except Exception as _e:
            _ta_logger.warning(f"[calculate_pivots] {df.attrs.get('symbol','?')}: {_e}")
            return {}

    @staticmethod
    def check_exhaustion(df: pd.DataFrame, current_price: float) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            current_date = df.index[-1].date()
            today_df = df[df.index.date == current_date]
            if today_df.empty: return {"is_exhausted": False}

            day_open = today_df['open'].iloc[0]
            
            # Calculate Daily ADR
            daily_highs = df.groupby(df.index.date)['high'].max()
            daily_lows = df.groupby(df.index.date)['low'].min()
            daily_ranges = daily_highs - daily_lows
            adr = daily_ranges.rolling(14, min_periods=1).mean().iloc[-1]
            if pd.isna(adr) or adr <= 0: adr = current_price * 0.015

            limit_price = day_open + (adr * 0.75)

            ema_20 = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
            atr = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range().iloc[-1]
            dist_from_ema = current_price - ema_20
            atr_multiple = dist_from_ema / max(atr, 1e-6)

            # Added Pioneer Check: Volume Climax
            vol_ma_val = IntradayTechnicalAnalysis.get_time_adjusted_vol_ma(df, df['volume'].rolling(20).mean())
            rvol_now = df['volume'].iloc[-1] / max(vol_ma_val, 1e-6)
            candle_spread = df['high'].iloc[-1] - df['low'].iloc[-1]
            
            is_vol_climax = rvol_now > 5.0 and candle_spread > (atr * 2.5)
            
            is_exhausted = current_price > limit_price or atr_multiple > 2.5 or is_vol_climax
            
            reasons = []
            if current_price > limit_price: reasons.append(f"Exhausted ADR limit: {current_price:.2f} > {limit_price:.2f}")
            if atr_multiple > 2.5: reasons.append(f"Deeply stretched from 20 EMA ({atr_multiple:.1f} ATRs)")
            if is_vol_climax: reasons.append(f"Volume Climax / Blow-Off Top Detected ({rvol_now:.1f}x Vol)")

            return {
                "is_exhausted": is_exhausted,
                "pct_from_open": round(((current_price - day_open) / day_open) * 100, 2),
                "atr_dist": round(atr_multiple, 2),
                "reasons": reasons
            }
        except Exception as _e:
            _ta_logger.warning(f"[check_exhaustion] {df.attrs.get('symbol','?')}: {_e}")
            return {"is_exhausted": False}

    @staticmethod
    def identify_pullback(df: pd.DataFrame, current_price: float) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            ema_9 = EMAIndicator(close=df['close'], window=9).ema_indicator().iloc[-1]
            vwap = IntradayTechnicalAnalysis.calculate_vwap(df)
            # Check if price is within 0.5% of either support
            near_ema = abs(current_price - ema_9) / current_price < 0.005
            near_vwap = abs(current_price - vwap) / max(current_price, 1e-6) < 0.005
            
            # Must be above 20 EMA to be a "Bullish" pullback
            ema_20 = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
            is_bullish = current_price > ema_20
            
            # Added Pioneer Check: Pullback Volume Contraction
            is_vol_contracting = False
            if len(df) >= 4:
                current_vol = df['volume'].iloc[-1]
                prev_vol = df['volume'].iloc[-2]
                impulse_vol = df['volume'].iloc[-4:-2].max()
                
                # Volume must be contracting on the pullback
                is_vol_contracting = (current_vol < impulse_vol) or (prev_vol < impulse_vol)
            else:
                is_vol_contracting = True # Pass if not enough data
                
            return {
                "is_pullback": (near_ema or near_vwap) and is_bullish and is_vol_contracting,
                "type": "9EMA" if near_ema else "VWAP" if near_vwap else "None",
                "support_val": ema_9 if near_ema else vwap if near_vwap else 0
            }
        except Exception as _e:
            _ta_logger.warning(f"[identify_pullback] {df.attrs.get('symbol','?')}: {_e}")
            return {"is_pullback": False}

    @staticmethod
    def calculate_ladder(df: pd.DataFrame, current_price: float) -> list:
        if df is None or df.empty: return []
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
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
    def detect_squeeze(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            bb = BollingerBands(close=df['close'], window=20, window_dev=2)
            h_band = bb.bollinger_hband()
            l_band = bb.bollinger_lband()
            bb_width = (h_band - l_band) / bb.bollinger_mavg()
            
            # Squeeze: Current width < 20-period SMA of width
            width_ma = bb_width.rolling(20).mean()
            is_squeeze = (bb_width.iloc[-1] if len(bb_width) > 0 else 0.0) < (width_ma.iloc[-1] if len(width_ma) > 0 else 0.0) * 0.95
            
            # Breakout: Current Close > Upper Band
            is_breakout = (df['close'].iloc[-1] if len(df['close']) > 0 else 0.0) > (h_band.iloc[-1] if len(h_band) > 0 else 0.0)
            
            return {
                "is_squeeze": is_squeeze,
                "is_breakout": is_breakout,
                "width": round((bb_width.iloc[-1] if len(bb_width) > 0 else 0.0), 4),
                # [V18 FIX #16] Prevent divide-by-zero on flat-price data
                "width_percentile": round(((bb_width.iloc[-1] if len(bb_width) > 0 else 0.0) / max((width_ma.iloc[-1] if len(width_ma) > 0 else 1.0), 1e-8)) * 100, 1),
                "upper": round((h_band.iloc[-1] if len(h_band) > 0 else 0.0), 2),
                "lower": round((l_band.iloc[-1] if len(l_band) > 0 else 0.0), 2)
            }
        except Exception as _e:
            _ta_logger.warning(f"[detect_squeeze] {df.attrs.get('symbol','?')}: {_e}")
            return {"is_squeeze": False, "is_breakout": False, "width": 0}

    @staticmethod
    def detect_rsi_divergence(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            # V15 Pioneer Fix: Shifted RSI to 9-period for highly responsive intraday momentum (was 14)
            rsi = RSIIndicator(close=df['close'], window=9).rsi()
            if len(df) < 30: return {"type": "None"}
            
            # FIX H4 & V2: Use macroscopic local swing highs/lows for proper peak-to-peak divergence
            # OLD: compared candle[-1] vs candle[-5] — arbitrary, not actual peaks
            # NEW: find local high/low in two windows (last 15 and prior 15) and compare
            window = 15
            # Recent swing: last 15 candles
            recent_price_high = df['close'].iloc[-window:].max()
            recent_price_high_idx = df['close'].iloc[-window:].idxmax()
            recent_price_low = df['close'].iloc[-window:].min()
            recent_price_low_idx = df['close'].iloc[-window:].idxmin()
            
            # Prior swing: 15-30 candles ago
            prior_price_high = df['close'].iloc[-(window*2):-window].max()
            prior_price_high_idx = df['close'].iloc[-(window*2):-window].idxmax()
            prior_price_low = df['close'].iloc[-(window*2):-window].min()
            prior_price_low_idx = df['close'].iloc[-(window*2):-window].idxmin()
            
            # RSI at those peaks
            recent_rsi_high = rsi.loc[recent_price_high_idx] if recent_price_high_idx in rsi.index else rsi.iloc[-1]
            prior_rsi_high = rsi.loc[prior_price_high_idx] if prior_price_high_idx in rsi.index else rsi.iloc[-15]
            recent_rsi_low = rsi.loc[recent_price_low_idx] if recent_price_low_idx in rsi.index else rsi.iloc[-1]
            prior_rsi_low = rsi.loc[prior_price_low_idx] if prior_price_low_idx in rsi.index else rsi.iloc[-15]
            
            # Bearish Divergence: Price Higher High but RSI Lower High (at overbought territory)
            if recent_price_high > prior_price_high and recent_rsi_high < prior_rsi_high and recent_rsi_high > 60:
                return {"type": "Bearish", "severity": "High" if recent_rsi_high < prior_rsi_high - 5 else "Moderate"}
            
            # Bullish Divergence: Price Lower Low but RSI Higher Low (at oversold territory)
            if recent_price_low < prior_price_low and recent_rsi_low > prior_rsi_low and recent_rsi_low < 40:
                return {"type": "Bullish", "severity": "High" if recent_rsi_low > prior_rsi_low + 5 else "Moderate"}
                
            return {"type": "None"}
        except Exception as _e:
            _ta_logger.warning(f"[detect_rsi_divergence] {df.attrs.get('symbol','?')}: {_e}")
            return {"type": "None"}

    @staticmethod
    def detect_wash_and_rinse(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if len(df) < 5: return {"is_trap": False}
            
            pivots = IntradayTechnicalAnalysis.calculate_pivots(df)
            vwap = IntradayTechnicalAnalysis.calculate_vwap(df) # Fixed: Use anchored VWAP
            levels = [vwap, pivots.get("S1", 0), pivots.get("P", 0)]
            
            last_3 = df.tail(3)
            current = last_3.iloc[-1]
            prev = last_3.iloc[-2]
            
            for lvl in levels:
                if lvl == 0: continue
                # Pattern: Prev low was below level, current close is above level + high volume
                if prev['low'] < lvl and current['close'] > lvl:
                    vol_spike = current['volume'] > df['volume'].rolling(14).mean().iloc[-1] * 1.5
                    if vol_spike:
                        return {
                            "is_trap": True, 
                            "level": "VWAP" if lvl == vwap else "S1" if lvl == pivots.get("S1") else "Pivot",
                            "strength": "High" if current['volume'] > df['volume'].rolling(14).mean().iloc[-1] * 2.5 else "Moderate"
                        }
            return {"is_trap": False}
        except Exception as _e:
            _ta_logger.warning(f"[detect_wash_and_rinse] {df.attrs.get('symbol','?')}: {_e}")
            return {"is_trap": False}

    @staticmethod
    def detect_bullish_fvg(df: pd.DataFrame) -> dict:
        """[V20 Vanguard] Detects Fair Value Gap (FVG) and verifies if current price is tapping it."""
        try:
            if len(df) < 5: return {"has_fvg": False}
            
            fvg_zone_top = 0
            fvg_zone_bottom = 0
            has_fvg = False
            
            # Check last 5 candles (excluding the current incomplete one) for FVG
            # Candle N-2 High < Candle N Low
            for i in range(-5, -2):
                c1_high = float(df['high'].iloc[i-2])
                c3_low = float(df['low'].iloc[i])
                
                if c3_low > c1_high: # Bullish Imbalance
                    fvg_zone_bottom = c1_high
                    fvg_zone_top = c3_low
                    has_fvg = True
                    break
                    
            current_low = float(df['low'].iloc[-1])
            is_tapping = has_fvg and (fvg_zone_bottom <= current_low <= fvg_zone_top)
            
            return {
                "has_fvg": has_fvg, 
                "is_tapping": is_tapping, 
                "zone": (fvg_zone_bottom, fvg_zone_top)
            }
        except Exception as _e:
            _ta_logger.warning(f"[detect_bullish_fvg] {df.attrs.get('symbol','?')}: {_e}")
            return {"has_fvg": False}

    @staticmethod
    def check_ema_fan(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            e9 = EMAIndicator(close=df['close'], window=9).ema_indicator().iloc[-1]
            e20 = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
            e50 = EMAIndicator(close=df['close'], window=50).ema_indicator().iloc[-1]
            e200 = EMAIndicator(close=df['close'], window=200).ema_indicator().iloc[-1]
            is_bullish_fan = e9 > e20 > e50 > e200
            is_bearish_fan = e9 < e20 < e50 < e200
            
            return {
                "status": "Bullish Fan" if is_bullish_fan else "Bearish Fan" if is_bearish_fan else "No Fan",
                "is_aligned": is_bullish_fan or is_bearish_fan,
                "score_bonus": 15 if is_bullish_fan else -15 if is_bearish_fan else 0
            }
        except Exception as _e:
            _ta_logger.warning(f"[check_ema_fan] {df.attrs.get('symbol','?')}: {_e}")
            return {"status": "No Fan", "is_aligned": False, "score_bonus": 0}

    @staticmethod
    def calculate_adx(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if len(df) < 20: return {"adx": 0, "status": "Unknown", "bias": "Neutral", "score": 50, "is_rising": False, "adx_slope": 0.0}
            
            adx_ind = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
            adx_series = adx_ind.adx()
            adx = adx_series.iloc[-1]
            plus_di = adx_ind.adx_pos().iloc[-1]
            minus_di = adx_ind.adx_neg().iloc[-1]
            
            # Trend Direction - Smoothing noise with 3-candle median
            adx_diff = adx_series.diff()
            adx_slope = adx_diff.rolling(window=3).median().iloc[-1] if len(adx_diff) >= 3 else adx_diff.iloc[-1]
            if np.isnan(adx_slope): adx_slope = 0.0
            
            is_rising = adx_slope > 0
            
            status = "Strong Trend" if adx > 25 else "Weak Trend" if adx < 20 else "Developing Trend"
            bias = "Bullish" if plus_di > minus_di else "Bearish"
            
            return {
                "adx": round(adx, 2),
                "adx_slope": round(adx_slope, 4),
                "is_rising": is_rising,
                "status": status,
                "bias": bias,
                "score": 100 if adx > 25 and plus_di > minus_di else 0 if adx > 25 and minus_di > plus_di else 50
            }
        except Exception as _e:
            _ta_logger.warning(f"[calculate_adx] {df.attrs.get('symbol','?')}: {_e}")
            return {"adx": 0, "status": "Unknown", "bias": "Neutral", "score": 50, "is_rising": False, "adx_slope": 0.0}

    @staticmethod
    def detect_volume_cluster(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if len(df) < 10: return {"is_cluster": False}
            
            # Use last 6 candles for 30 min window (if 5m interval) or last 3 (if 10m)
            # Standardizing to check the trailing segment of the dataframe
            # Since df_15m is used in the engine, 30m = 2 candles. 
            # However, the requirement is "3 consecutive candles". 
            # We will use the last 6 candles from the dataframe (assuming 5m or 15m context)
            
            vol_ma_val = IntradayTechnicalAnalysis.get_time_adjusted_vol_ma(df, df['volume'].rolling(20).mean())
            
            # We check a rolling window of 3 for the condition
            # 1. Volume > MA
            # 2. Close > Open (Rising)
            cond_vol = df['volume'] > vol_ma_val
            cond_price = df['close'] > df['open']
            
            # Combined condition
            cluster_mask = cond_vol & cond_price
            
            # Check for 3 consecutive True in the last 6 candles
            trailing_mask = cluster_mask.tail(6)
            
            is_cluster = False
            for i in range(len(trailing_mask) - 2):
                if trailing_mask.iloc[i:i+3].all():
                    is_cluster = True
                    break
            
            return {
                "is_cluster": is_cluster,
                "reasons": ["Sequential abnormal volume + rising price"] if is_cluster else []
            }
        except Exception as _e:
            _ta_logger.warning(f"[detect_volume_cluster] {df.attrs.get('symbol','?')}: {_e}")
            return {"is_cluster": False}

    @staticmethod
    def detect_micro_trend(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if len(df) < 10: return {"pattern": "None", "hh_hl": False, "lh": False}

            last_10 = df.tail(10)
            # Compare last 5 vs previous 5 within the 10-candle window
            mid = len(last_10) // 2
            first_half = last_10.iloc[:mid]
            second_half = last_10.iloc[mid:]

            max_first = first_half['high'].max()
            min_first = first_half['low'].min()
            max_second = second_half['high'].max()
            min_second = second_half['low'].min()

            hh_hl = (max_second > max_first) and (min_second > min_first)
            lh = (max_second < max_first)

            pattern = "HH-HL" if hh_hl else "Lower High" if lh else "None"

            return {
                "pattern": pattern,
                "hh_hl": hh_hl,
                "lh": lh
            }
        except Exception as _e:
            _ta_logger.warning(f"[detect_micro_trend] {df.attrs.get('symbol','?')}: {_e}")
            return {"pattern": "None", "hh_hl": False, "lh": False}

    @staticmethod
    def detect_stop_hunt_sweep(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if len(df) < 30: return {"liquidity_sweep": False}

            latest = df.iloc[-1]
            prev_1 = df.iloc[-2]
            prev_2 = df.iloc[-3] if len(df) > 2 else prev_1
            
            # 1. BREAKOUT LEVEL IDENTIFICATION
            # A. Intraday Swing High (Last 1 hour / 4 candles of 15m)
            _high = df['high']
            high_series = _high.iloc[:, 0] if isinstance(_high, pd.DataFrame) else _high
            swing_high = high_series.iloc[-5:-1].max()
            
            # B. Opening Range High (Strict 09:15 to 09:45)
            orb_high = 0
            if isinstance(df.index, pd.DatetimeIndex):
                try:
                    if df.index.tz is None: df.index = df.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
                    else: df.index = df.index.tz_convert('Asia/Kolkata')
                except:
                    pass
                current_date = df.index[-1].date()
                today_df = df[df.index.date == current_date]
                if not today_df.empty:
                    start_time = pd.Timestamp.combine(current_date, pd.to_datetime('09:15:00').time())
                    end_time = pd.Timestamp.combine(current_date, pd.to_datetime('09:45:00').time())
                    if today_df.index.tz is not None:
                        start_time = start_time.tz_localize('Asia/Kolkata')
                        end_time = end_time.tz_localize('Asia/Kolkata')
                    orb_df = today_df[(today_df.index >= start_time) & (today_df.index <= end_time)]
                    if not orb_df.empty:
                        orb_high = orb_df['high'].max()
            
            # C. VWAP Deviation resistance (Approximation)
            _low = df['low']
            _close = df['close']
            low_series = _low.iloc[:, 0] if isinstance(_low, pd.DataFrame) else _low
            close_series = _close.iloc[:, 0] if isinstance(_close, pd.DataFrame) else _close
            _vol = df['volume']
            vol_series = _vol.iloc[:, 0] if isinstance(_vol, pd.DataFrame) else _vol
            
            tp = (high_series + low_series + close_series) / 3
            vwap = (tp * vol_series).cumsum() / vol_series.cumsum()
            vwap_now = safe_scalar(vwap.iloc[-1])
            std_dev = close_series.rolling(20).std().iloc[-1]
            vwap_res = vwap_now + (2 * std_dev)
            
            # D. Previous Day High
            pdh = 0
            if isinstance(df.index, pd.DatetimeIndex):
                dates = pd.Series(df.index.date).unique()
                if len(dates) > 1:
                    prev_day = dates[-2]
                    prev_day_df = df[df.index.date == prev_day]
                    _pd_high = prev_day_df['high']
                    pd_high_series = _pd_high.iloc[:, 0] if isinstance(_pd_high, pd.DataFrame) else _pd_high
                    pdh = pd_high_series.max()
            
            # Identify the MOST RELEVANT breakout level (The major resistance we are testing)
            # Upgrade 1 V4.2: Priority Level Selection (Major > Minor)
            # Priority: Prev_Day_High > OR_High > Swing_High
            
            _close_val = latest['close']
            current_price = safe_scalar(_close_val)
            breakout_level = 0
            breakout_level_source = "None"
            
            # [PHASE 2 FIX] ATR-Aware Proximity Threshold
            # Replaced rigid 3% band with 1.5 ATR to adapt to high-VIX environments
            try:
                from ta.volatility import AverageTrueRange
                _atr_series = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
                atr = _atr_series.iloc[-1]
                if pd.isna(atr) or atr == 0: atr = current_price * 0.015
            except Exception:
                atr = current_price * 0.015
                
            proximity_band = max(1.5 * atr, current_price * 0.005)
            
            # 1. Higher Priority: Previous Day High
            if pdh > 0 and current_price > 0 and abs(pdh - current_price) < proximity_band:
                breakout_level = pdh
                breakout_level_source = "Prev_Day_High"
            
            # 2. Medium Priority: Opening Range High (If PDH not valid)
            elif orb_high > 0 and current_price > 0 and abs(orb_high - current_price) < proximity_band:
                breakout_level = orb_high
                breakout_level_source = "OR_High"
                
            # 3. Standard Priority: Swing High (If others not valid)
            elif swing_high > 0 and current_price > 0 and abs(swing_high - current_price) < proximity_band:
                breakout_level = swing_high
                breakout_level_source = "Swing_High"
                
            # 4. Fallback: VWAP Res
            elif vwap_res > 0 and current_price > 0 and abs(vwap_res - current_price) < proximity_band:
                breakout_level = vwap_res
                breakout_level_source = "VWAP_Res"
            
            if breakout_level <= 0: return {"liquidity_sweep": False}

            # 2. BREAKOUT DETECTION (In last 3 candles)
            # Upgrade V5: Categorize breakout strength and failures
            had_breakout = False
            breakout_index = -1
            breakout_strength = 0.0
            is_weak_breakout = False
            
            # Use current close for strength if we are above
            _l_close = latest['close']
            l_close_val = safe_scalar(_l_close)
            if l_close_val > breakout_level:
                breakout_strength = (l_close_val - breakout_level) / breakout_level
                if breakout_strength < 0.003:
                    is_weak_breakout = True
            
            for i in range(-3, 0):
                _c_high = df.iloc[i]['high']
                _c_close = df.iloc[i]['close']
                c_high_val = safe_scalar(_c_high)
                c_close_val = safe_scalar(_c_close)
                if c_high_val > breakout_level and c_close_val > breakout_level:
                    had_breakout = True
                    breakout_index = i
                    # Capture strength from the actual breakout candle if needed
                    breakout_strength = max(breakout_strength, (c_close_val - breakout_level) / breakout_level)
                    break

            # 3. LIQUIDITY SWEEP DETECTION
            liquidity_sweep = False
            stop_hunt_detected = False
            
            # Condition A: Wick High > Level AND Close < Level (Immediate Rejection)
            _l_high = latest['high']
            l_high_val = safe_scalar(_l_high)
            _l_close = latest['close']
            l_close_val = safe_scalar(_l_close)
            cond_a = l_high_val > breakout_level and l_close_val < breakout_level
            
            # Condition B: Closes back below within 2 candles (FAILED_BREAKOUT)
            cond_b = False
            fake_breakout_flag = False
            if had_breakout:
                # If we had a breakout in the last 2 candles but current price is below
                # breakout_index: -1 (last), -2 (prev), -3 (2nd prev)
                # If breakout was at -3 or -2 and now we are back below (latest is -1)
                _l_close = latest['close']
                l_close_val = safe_scalar(_l_close)
                if breakout_index < -1 and l_close_val < breakout_level:
                    cond_b = True
                    fake_breakout_flag = True
            
            # Condition C: Volume spike but fail to hold
            _vol_all = df['volume']
            vol_series = _vol_all.iloc[:, 0] if isinstance(_vol_all, pd.DataFrame) else _vol_all
            _vol_ma_res = vol_series.rolling(20).mean().iloc[-1]
            vol_ma = safe_scalar(_vol_ma_res)
            
            _l_vol = latest['volume']
            l_vol_val = safe_scalar(_l_vol)
            rvol = l_vol_val / max(vol_ma, 1e-6)
            
            _l_high = latest['high']
            l_high_val = safe_scalar(_l_high)
            _l_close = latest['close']
            l_close_val = safe_scalar(_l_close)
            cond_c = rvol > 1.8 and l_high_val > breakout_level and l_close_val < breakout_level
            
            if cond_a or cond_b or cond_c:
                liquidity_sweep = True
            
            # 4. STOP HUNT CONFIRMATION
            _l_close = latest['close']
            l_close_val = safe_scalar(_l_close)
            if liquidity_sweep and rvol > 1.8 and l_close_val < breakout_level:
                stop_hunt_detected = True

            # 5. STATEFUL RE-ENTRY CHECK (Module 3 V4)
            # Count consecutive candles closing above the level at the end of the DF
            candle_hold_count = 0
            _close = df['close']
            close_series = _close.iloc[:, 0] if isinstance(_close, pd.DataFrame) else _close
            for i in range(len(df)-1, -1, -1):
                if close_series.iloc[i] > breakout_level:
                    candle_hold_count += 1
                else:
                    break
            
            # Volume check: average volume over the hold duration (capped at 3 for rule validation)
            check_count = max(1, min(candle_hold_count, 3))
            _vol = df['volume']
            vol_series = _vol.iloc[:, 0] if isinstance(_vol, pd.DataFrame) else _vol
            reclaim_vol_avg = vol_series.iloc[-check_count:].mean() if candle_hold_count > 0 else 0
            
            price_reclaim = False
            if candle_hold_count >= 2 and reclaim_vol_avg >= vol_ma:
                price_reclaim = True

            return {
                "liquidity_sweep": liquidity_sweep,
                "stop_hunt_detected": stop_hunt_detected,
                "fake_breakout_flag": fake_breakout_flag,
                "breakout_strength": round(breakout_strength, 4),
                "is_weak_breakout": is_weak_breakout,
                "is_breakout": l_close_val > breakout_level,
                "breakout_level": float(breakout_level),
                "breakout_level_source": breakout_level_source,
                "price_reclaim": price_reclaim,
                "candle_hold_count": candle_hold_count,
                "reclaim_vol_avg": round(reclaim_vol_avg, 1),
                "rvol": round(rvol, 2),
                "tag": "[⚠ FAILED BREAKOUT]" if fake_breakout_flag else ("[⚠ Liquidity Sweep Trap]" if liquidity_sweep and not price_reclaim else "")
            }
        except Exception as e:
            print(f"Error in Sweep Detection: {e}")
            return {"liquidity_sweep": False}

    @staticmethod
    def detect_trend_direction(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if len(df) < 50: return {"trend_direction_state": "NEUTRAL_TREND", "ema_alignment": False}
            
            _close = df['close']
            close_series = _close.iloc[:, 0] if isinstance(_close, pd.DataFrame) else _close
            ema_20_series = EMAIndicator(close=close_series, window=20).ema_indicator()
            ema_50_series = EMAIndicator(close=close_series, window=50).ema_indicator()
            ema_20 = ema_20_series.iloc[-1]
            ema_20_prev = ema_20_series.iloc[-2]
            ema_50 = ema_50_series.iloc[-1]
            
            ema_alignment = ema_20 > ema_50
            slope_20 = ema_20 - ema_20_prev
            
            # Use 0.01% of price as a threshold for "positive" slope to avoid noise
            slope_threshold = ema_20 * 0.0001
            
            if not ema_alignment:
                state = "BEARISH_TREND"
            elif slope_20 > slope_threshold:
                state = "BULLISH_TREND"
            else:
                state = "NEUTRAL_TREND"
                
            return {
                "trend_direction_state": state,
                "ema_alignment": ema_alignment,
                "ema_20": round(ema_20, 2),
                "ema_50": round(ema_50, 2),
                "slope_20": round(slope_20, 4)
            }
        except Exception as e:
            print(f"Error in Trend Direction Detection: {e}")
            return {"trend_direction_state": "NEUTRAL_TREND", "ema_alignment": False}

    @staticmethod
    def detect_market_structure(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if len(df) < 6: return {"market_structure_state": "NEUTRAL_STRUCTURE"}
            
            # Lookback window: last 5 candles excluding current
            # prev_window = df.iloc[-6:-1]
            _high_all = df['high']
            _low_all = df['low']
            h_s = _high_all.iloc[:, 0] if isinstance(_high_all, pd.DataFrame) else _high_all
            l_s = _low_all.iloc[:, 0] if isinstance(_low_all, pd.DataFrame) else _low_all
            
            _ph = h_s.iloc[-6:-1].max()
            _pl = l_s.iloc[-6:-1].min()
            prev_high = safe_scalar(_ph)
            prev_low = safe_scalar(_pl)
            
            _lh = h_s.iloc[-1]
            _ll = l_s.iloc[-1]
            latest_high = safe_scalar(_lh)
            latest_low = safe_scalar(_ll)
            
            # Structure rules
            # Bullish: Higher High + Higher Low
            if latest_high > prev_high and latest_low > prev_low:
                state = "BULLISH_STRUCTURE"
            # Bearish: Lower High + Lower Low (Stricter than previous V6 logic)
            elif latest_high < prev_high and latest_low < prev_low:
                state = "BEARISH_STRUCTURE"
            else:
                state = "NEUTRAL_STRUCTURE"
                
            return {
                "market_structure_state": state,
                "latest_high": round(float(latest_high), 2),
                "latest_low": round(float(latest_low), 2),
                "prev_high": round(float(prev_high), 2),
                "prev_low": round(float(prev_low), 2)
            }
        except Exception as e:
            print(f"Error in Market Structure Detection: {e}")
            return {"market_structure_state": "NEUTRAL_STRUCTURE"}

    @staticmethod
    def detect_liquidity_trap(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if len(df) < 20: return {"trap_move_detected": False}
            
            latest = df.iloc[-1]
            
            # 1. Volume spike ratio > 1.8x volume_ma(10)
            _vol_all = df['volume']
            vol_series = _vol_all.iloc[:, 0] if isinstance(_vol_all, pd.DataFrame) else _vol_all
            vol_ma_all = vol_series.rolling(10).mean()
            _vol_ma_val = vol_ma_all.iloc[-2] if not np.isnan(vol_ma_all.iloc[-2]) else (vol_ma_all.iloc[-1] if len(vol_ma_all) > 0 else 0.0)
            vol_ma = safe_scalar(_vol_ma_val)
            
            _l_vol = latest['volume']
            l_vol_val = safe_scalar(_l_vol)
            volume_spike_ratio = l_vol_val / max(vol_ma, 1e-6)
            cond_vol = volume_spike_ratio > 1.8
            
            # 2. Upper wick > 50% of candle
            _l_high = latest['high']
            l_high_val = safe_scalar(_l_high)
            _l_low = latest['low']
            l_low_val = safe_scalar(_l_low)
            _l_close = latest['close']
            l_close_val = safe_scalar(_l_close)
            _l_open = latest['open']
            l_open_val = safe_scalar(_l_open)
            
            candle_range = l_high_val - l_low_val
            upper_wick = l_high_val - max(l_close_val, l_open_val)
            upper_wick_ratio = upper_wick / candle_range if candle_range > 0 else 0
            cond_wick = upper_wick_ratio > 0.50
            
            # 3. Close position formula (low to high range ratio)
            # close_position = (close - low) / (high - low)
            close_position = (l_close_val - l_low_val) / candle_range if candle_range > 0 else 0.5
            cond_close = close_position <= 0.30
            
            # 4. Range Expansion Check [V18 FIX #3: was missing, causing NameError]
            atr_trap_series = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
            atr_trap_val = float(atr_trap_series.iloc[-1]) if not atr_trap_series.empty else max(candle_range, 1e-6)
            range_expansion_ratio = candle_range / max(atr_trap_val, 1e-6)
            cond_range = range_expansion_ratio > 1.5  # Range > 1.5x ATR = abnormal expansion
            
            # 5. Divergent Volume Check (V17 Vanguard)
            # Volume is rising while price fails to make new highs (Distribution)
            vol_slope = vol_series.iloc[-5:].diff().mean()
            price_slope = df['high'].iloc[-5:].diff().mean()
            is_divergent = vol_slope > 0 and price_slope <= 0 and l_close_val < l_open_val
            
            trap_move_detected = (cond_vol and cond_wick and cond_close and cond_range) or (is_divergent and cond_vol)
            
            return {
                "trap_move_detected": trap_move_detected,
                "is_divergent": is_divergent,
                "trap_range_expansion": cond_range, 
                "range_expansion_ratio": round(range_expansion_ratio, 2),
                "details": {
                    "vol_spike": cond_vol,
                    "upper_wick_ratio": round(upper_wick_ratio, 2),
                    "close_position": round(close_position, 2),
                    "range_expansion_ratio": round(range_expansion_ratio, 2),
                    "divergent_vol": is_divergent
                }
            }
        except Exception as e:
            # print(f"Error in Liquidity Trap Detection: {e}") # Debugging
            return {"trap_move_detected": False, "trap_range_expansion": False}

    @staticmethod
    def detect_liquidity_sweep_enhanced(df: pd.DataFrame, is_short: bool = False) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if len(df) < 21:
                return {"is_sweep": False, "range_low": 0.0, "volume_spike": 0.0}

            # 1. Look at last 20 candles (excluding CURRENT)
            analysis_range = df.iloc[-21:-1]
            latest = df.iloc[-1]

            _lows = analysis_range['low']
            lows_series = _lows.iloc[:, 0] if isinstance(_lows, pd.DataFrame) else _lows
            range_low = float(lows_series.min())
            
            _highs = analysis_range['high']
            highs_series = _highs.iloc[:, 0] if isinstance(_highs, pd.DataFrame) else _highs
            range_high = float(highs_series.max())

            # 2. Latest Candle Logic
            _l_low = latest['low']
            l_low_val = safe_scalar(_l_low)
            _l_high = latest['high']
            l_high_val = safe_scalar(_l_high)
            _l_close = latest['close']
            l_close_val = safe_scalar(_l_close)
            
            candle_range = l_high_val - l_low_val if l_high_val > l_low_val else (l_low_val * 0.001)
            
            if is_short:
                wick_strength = (l_high_val - l_close_val) / candle_range
                strong_rejection = wick_strength > 0.4  # 40% of candle must be top wick
            else:
                wick_strength = (l_close_val - l_low_val) / candle_range
                strong_rejection = wick_strength > 0.4  # 40% of candle must be bottom wick

            ema_20_series = EMAIndicator(close=df['close'], window=20).ema_indicator()
            ema_20 = float(ema_20_series.iloc[-1])
            trend_filter = l_close_val < ema_20 if is_short else l_close_val > ema_20

            _p_close = df['close'].iloc[-2]
            prev_close_val = safe_scalar(_p_close)
            
            if is_short:
                sustained_reclaim = l_close_val < range_high and prev_close_val < range_high
                sweep_size = (l_high_val - range_high) / (range_high if range_high > 0 else 1.0)
                valid_sweep_size = sweep_size > 0.0015
                break_detected = l_high_val > (range_high * 1.002)
                reclaim_detected = l_close_val < range_high
            else:
                sustained_reclaim = l_close_val > range_low and prev_close_val > range_low
                sweep_size = (range_low - l_low_val) / (range_low if range_low > 0 else 1.0)
                valid_sweep_size = sweep_size > 0.0015
                break_detected = l_low_val < (range_low * 0.998)
                reclaim_detected = l_close_val > range_low

            _volumes_lookback = df['volume'].iloc[-21:-1]
            vol_series_lk = _volumes_lookback.iloc[:, 0] if isinstance(_volumes_lookback, pd.DataFrame) else _volumes_lookback
            vol_ma = float(vol_series_lk.mean())
            
            _l_vol = latest['volume']
            l_vol_val = safe_scalar(_l_vol)
            
            volume_spike_ratio = l_vol_val / max(vol_ma, 1e-6)
            volume_confirmed = volume_spike_ratio >= 1.5

            sweep_score = 0
            if break_detected: sweep_score += 20
            if reclaim_detected: sweep_score += 20
            if volume_confirmed: sweep_score += 20
            if strong_rejection: sweep_score += 20
            if valid_sweep_size: sweep_score += 20

            is_sweep = (sweep_score >= 80 and sustained_reclaim)

            return {
                "is_sweep": is_sweep,
                "sweep_score": sweep_score,
                "range_low": round(range_low, 2),
                "range_high": round(range_high, 2),
                "volume_spike": round(volume_spike_ratio, 2),
                "sweep_type": ("bearish" if is_short else "bullish") if is_sweep else "none"
            }
        except Exception as e:
            return {"is_sweep": False, "range_low": 0.0, "range_high": 0.0, "volume_spike": 0.0}

    @staticmethod
    def detect_breakout_engine_v4(df: pd.DataFrame, consolidation_high: float, vwap: float, sweep_ctx: dict) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            latest = df.iloc[-1]
            
            # --- 0. DATA EXTRACTION (Handle Duplicates/Series) ---
            _l_close = latest['close']
            l_close_val = safe_scalar(_l_close)
            _l_high = latest['high']
            l_high_val = safe_scalar(_l_high)
            _l_low = latest['low']
            l_low_val = safe_scalar(_l_low)
            _l_vol = latest['volume']
            l_vol_val = safe_scalar(_l_vol)

            # --- V4.2 PRE-REQUISITES (ATR 14) ---
            atr_series = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
            atr_val = float(atr_series.iloc[-2])
            # Safety fallback for ATR
            atr_val = atr_val if atr_val > 0 else (l_close_val * 0.001)

            # 1. BREAKOUT STRENGTH (25 pts)
            strength_score = 0
            is_strong_breakout = l_close_val > (consolidation_high * 1.0015)
            if is_strong_breakout: strength_score = 25

            # 2. VOLUME CONFIRMATION (25 pts)
            vol_ma_series = df['volume'].iloc[-21:-1]
            vol_series_lk = vol_ma_series.iloc[:, 0] if isinstance(vol_ma_series, pd.DataFrame) else vol_ma_series
            vol_ma = float(vol_series_lk.mean())
            vol_ratio = l_vol_val / max(vol_ma, 1e-6)
            
            volume_score = 0
            if vol_ratio > 2.0: volume_score = 25
            elif vol_ratio > 1.5: volume_score = 20
            elif vol_ratio > 1.2: volume_score = 10

            # 3. CANDLE STRENGTH (20 pts)
            candle_range = l_high_val - l_low_val
            candle_strength = (l_close_val - l_low_val) / candle_range if candle_range > 0 else 1.0
            candle_score = 20 if candle_strength > 0.75 else 0

            # 4. VWAP CONFIRMATION (10 pts)
            vwap_score = 10 if l_close_val > vwap else 0

            # 5. TREND CONFIRMATION (EMA 9/20) (10 pts)
            ema9_series = EMAIndicator(close=df['close'], window=9).ema_indicator()
            ema20_series = EMAIndicator(close=df['close'], window=20).ema_indicator()
            ema9 = float(ema9_series.iloc[-2])
            ema20 = float(ema20_series.iloc[-2])
            trend_aligned = ema9 > ema20 and l_close_val > ema9
            trend_score = 10 if trend_aligned else 0

            # 6. LIQUIDITY CONTEXT (10 pts bonus)
            liquidity_bonus = 10 if sweep_ctx.get("is_sweep", False) else 0

            # --- V4.2 NEW ADVANCED FILTERS ---
            # 7. FALSE BREAKOUT FILTER & ABSORPTION REWARD (V4.3)
            trap_risk = False
            trap_penalty = 0
            absorption_bonus = 0
            wicks_above_res = 0
            
            # Check last 10 candles before current breakout candle
            for i in range(-11, -1):
                if i >= -len(df):
                    _h_prev = df['high'].iloc[i]
                    _c_prev = df['close'].iloc[i]
                    _o_prev = df['open'].iloc[i]
                    _l_prev = df['low'].iloc[i]
                    
                    hp_val = safe_scalar(_h_prev)
                    cp_val = safe_scalar(_c_prev)
                    op_val = safe_scalar(_o_prev)
                    lp_val = safe_scalar(_l_prev)
                    
                    if hp_val > consolidation_high and cp_val < consolidation_high:
                        # Deep rejection check: did it close near the low of the candle?
                        prev_range = hp_val - lp_val if hp_val > lp_val else 1e-6
                        close_pos = (cp_val - lp_val) / prev_range
                        if close_pos < 0.3:
                            trap_risk = True # Deep rejection (bearish fakeout)
                        else:
                            wicks_above_res += 1 # Shallow tap (bullish absorption)
            
            if trap_risk: 
                trap_penalty = 10
            elif wicks_above_res >= 2:
                # Multiple taps without deep rejections = Coiling/Ascending Triangle
                absorption_bonus = 10

            # 8. EXPANSION vs EXHAUSTION (15 pts)
            expansion_ratio = candle_range / max(atr_val, 1e-6)
            expansion_score = 0
            if expansion_ratio > 1.5: expansion_score = 15
            elif expansion_ratio >= 1.0: expansion_score = 8

            # 9. BREAKOUT LOCATION QUALITY (15 pts)
            dist_vwap_atr = abs(l_close_val - vwap) / max(atr_val, 1e-6)
            location_score = 0
            if dist_vwap_atr < 1.0: location_score = 15
            elif dist_vwap_atr <= 2.0: location_score = 8

            # 10. FINAL SCORING (SUM OF ALL)
            # R4-11 FIX: Normalize score to max 100
            breakout_score = min(100, (
                strength_score + 
                volume_score + 
                candle_score + 
                vwap_score + 
                trend_score + 
                liquidity_bonus + 
                expansion_score + 
                location_score +
                absorption_bonus - 
                trap_penalty
            ))
            
            # Classification
            if breakout_score >= 80: strength_label = "Explosive Breakout"
            elif breakout_score >= 60: strength_label = "Valid Breakout"
            elif breakout_score >= 40: strength_label = "Weak Breakout"
            else: strength_label = "Fakeout Risk"

            return {
                "is_breakout": breakout_score >= 60,
                "breakout_score": breakout_score,
                "breakout_strength": strength_label,
                "volume_ratio": round(vol_ratio, 2),
                "candle_strength": round(candle_strength, 2),
                "above_vwap": l_close_val > vwap,
                "trend_aligned": trend_aligned,
                "expansion_ratio": round(expansion_ratio, 2),
                "distance_from_vwap_atr": round(dist_vwap_atr, 2),
                "trap_risk": trap_risk,
                "absorption_bonus": absorption_bonus  # V18 FIX #4: removed undefined vars
            }
        except Exception as e:
            # print(f"Error in Breakout Engine: {e}")
            return {
                "is_breakout": False, 
                "breakout_score": 0, 
                "breakout_strength": "Error", 
                "volume_ratio": 0.0, 
                "candle_strength": 0.0, 
                "above_vwap": False, 
                "trend_aligned": False,
                "trap_risk": False,
                "absorption_bonus": 0
            }

    @staticmethod
    def detect_pullback_entry_v45(df: pd.DataFrame, breakout_level: float, context: dict = None, is_short: bool = False) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if len(df) < 25: return {"is_entry": False}

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            # --- 0. DATA EXTRACTION (Scalars) ---
            _l_open = latest['open']; l_open_val = safe_scalar(_l_open)
            _l_close = latest['close']; l_close_val = safe_scalar(_l_close)
            _l_high = latest['high']; l_high_val = safe_scalar(_l_high)
            _l_low = latest['low']; l_low_val = safe_scalar(_l_low)
            _l_vol = latest['volume']; l_vol_val = safe_scalar(_l_vol)

            _p_high = prev['high']; p_high_val = safe_scalar(_p_high)
            _p_close = prev['close']; p_close_val = safe_scalar(_p_close)
            _p_low = prev['low']; p_low_val = safe_scalar(_p_low)

            # --- INDICATORS ---
            ema9_series = EMAIndicator(close=df['close'], window=9).ema_indicator()
            ema20_series = EMAIndicator(close=df['close'], window=20).ema_indicator()
            ema50_series = EMAIndicator(close=df['close'], window=50).ema_indicator()
            ema9_val = float(ema9_series.iloc[-2])
            ema20_val = float(ema20_series.iloc[-2])
            ema50_val = float(ema50_series.iloc[-2])
            
            # Calculate VWAP up to the closed candle to prevent live tick repainting
            vwap = IntradayTechnicalAnalysis.calculate_vwap(df.iloc[:-1])
            atr_series = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
            atr_val = float(atr_series.iloc[-2])
            atr_val = atr_val if atr_val > 0 else (l_close_val * 0.001)

            vol_ma_series = df['volume'].iloc[-21:-1]
            v20_avg = float(vol_ma_series.mean())
            
            last_3_vol = df['volume'].iloc[-3:]
            prev_10_vol = df['volume'].iloc[-13:-3]
            v3_avg = float(last_3_vol.mean())
            v10_avg = float(prev_10_vol.mean())

            # --- 0.1 INTEGRITY & L1 MICRO-PARAMS [V13] ---
            v_adj = atr_val / l_close_val
            # Clamped Adaptive Gate: Widens for volatile stocks (min 0.3, max 0.8 ATR)
            adaptive_gate = min(max(0.4 * (1 + (v_adj * 10)), 0.3), 0.8)
            
            # Normalized Trend Strength: Price-agnostic EMA spread
            trend_strength = abs(ema20_val - ema50_val) / l_close_val
            
            # --- 0.2 ADVANCED L1 PATTERNS [V13] ---
            # 1. High Velocity Reclaim/Breakdown (Structure Reversal)
            swing_low_series = df['low'].iloc[-6:-1]
            swing_high_series = df['high'].iloc[-6:-1]
            prev_swing_low = float(swing_low_series.min())
            prev_swing_high = float(swing_high_series.max())
            
            if is_short:
                reclaim_velocity = (l_high_val - l_close_val) / max(atr_val, 1e-6)
                hv_reclaim = (reclaim_velocity > 0.5) and (l_close_val < prev_swing_high) and (l_close_val < vwap)
            else:
                reclaim_velocity = (l_close_val - l_low_val) / max(atr_val, 1e-6)
                hv_reclaim = (reclaim_velocity > 0.5) and (l_close_val > prev_swing_low) and (l_close_val > vwap)
            
            # 2. Volatility Squeeze (Compression)
            squeeze_detected = (atr_val / l_close_val) < 0.005 # Tight consolidation
            
            # 3. Stop-Hunt Reversal (Shakeout / Trap)
            if is_short:
                failed_breakout = (l_high_val > prev_swing_high) and (l_close_val < prev_swing_high)
                stop_hunt_reversal = failed_breakout and (l_vol_val > (v20_avg * 1.5))
            else:
                failed_breakdown = (l_low_val < prev_swing_low) and (l_close_val > prev_swing_low)
                stop_hunt_reversal = failed_breakdown and (l_vol_val > (v20_avg * 1.5))
            
            # 4. Liquidity Vacuum (Ghost Move)
            price_delta_pct = abs(l_close_val - l_open_val) / l_open_val
            liquidity_vacuum = (price_delta_pct > 0.005) and (l_vol_val < (v20_avg * 0.5))

            # --- 2. PULLBACK DEFINITION (30 pts) (V4.6 ADAPTIVE ATR-NORMALIZED) ---
            # V16.1: Adaptive proximity based on beta/volatility context
            vol_mult = context.get("vol_mult", 1.0) if context else 1.0
            gate_size = 0.4 * vol_mult # Scales gate from 0.4 to 0.6 for high-beta
            
            if is_short:
                dist_ema9_atr = abs(l_high_val - ema9_val) / max(atr_val, 1e-6)
                dist_retest_atr = abs(l_high_val - breakout_level) / max(atr_val, 1e-6)
                vwap_pierced = (l_high_val > vwap) and (l_close_val < vwap)
            else:
                dist_ema9_atr = abs(l_low_val - ema9_val) / max(atr_val, 1e-6)
                dist_retest_atr = abs(l_low_val - breakout_level) / max(atr_val, 1e-6)
                vwap_pierced = (l_low_val < vwap) and (l_close_val > vwap)

            pullback_score = 0
            entry_type = "None"
            
            # Use a weighted approach for "Near Hits" (Fractional Alpha)
            def calculate_proximity_score(dist, gate):
                if dist < gate: return 30
                if dist < gate * 1.5: return 15 # "Near Miss" reward
                return 0

            s_ema = calculate_proximity_score(dist_ema9_atr, gate_size)
            # [GAP 3 FIX] VWAP requires an actual liquidity sweep piercing, no near misses
            s_vwap = 30 if vwap_pierced else 0
            s_retest = calculate_proximity_score(dist_retest_atr, gate_size)
            
            pullback_score = max(s_ema, s_vwap, s_retest)
            if s_ema == 30: entry_type = "EMA Pullback"
            elif s_vwap == 30: entry_type = "VWAP Bounce"
            elif s_retest == 30: entry_type = "Retest"
            elif pullback_score == 15: entry_type = "Loose Pullback"

            # --- 3. TREND & SAFETY (20 pts) ---
            local_high = float(df['high'].tail(5).max())
            local_low = float(df['low'].tail(5).min())
            
            if is_short:
                pullback_depth_atr = (l_high_val - local_low) / max(atr_val, 1e-6)
                trend_hold = l_close_val < ema20_val
            else:
                pullback_depth_atr = (local_high - l_low_val) / max(atr_val, 1e-6)
                trend_hold = l_close_val > ema20_val
                
            depth_ok = pullback_depth_atr < 1.0
            
            prev_candle_range = p_high_val - p_low_val
            prev_candle_strength = (p_close_val - p_low_val) / prev_candle_range if prev_candle_range > 0 else 0.5
            
            if is_short:
                no_strong_counter = prev_candle_strength < 0.75  # No strong bullish candle preceding
            else:
                no_strong_counter = prev_candle_strength > 0.25  # No strong bearish candle preceding

            trend_score = 0
            if trend_hold and depth_ok and no_strong_counter:
                trend_score = 20

            # --- 4. ENTRY TRIGGER (30 pts) [V5.5] ---
            c_range = l_high_val - l_low_val
            c_strength = (l_close_val - l_low_val) / c_range if c_range > 0 else 0.5
            
            if is_short:
                reversal_trigger = (l_close_val < p_low_val) and (c_strength < 0.3) and (l_close_val < l_open_val)
            else:
                reversal_trigger = (l_close_val > p_high_val) and (c_strength > 0.7) and (l_close_val > l_open_val)
                
            trigger_score = 30 if reversal_trigger else 0

            # --- 5. VOLUME CONFIRMATION (20 pts) [V5.7 HYBRID] ---
            # Rewards either Expansion (Breakout) or Contraction (Healthy Pullback)
            vol_ma_series = df['volume'].iloc[-21:-1]
            vol_series_lk = vol_ma_series.iloc[:, 0] if isinstance(vol_ma_series, pd.DataFrame) else vol_ma_series
            vol_ma = float(vol_series_lk.mean())
            vol_ratio = l_vol_val / max(vol_ma, 1e-6)
            
            # Hybrid Logic
            volume_expansion = vol_ratio >= 1.2
            volume_contraction = v3_avg < v10_avg # Institutional "Resting" orders
            
            if volume_expansion:
                volume_score = 20
            elif volume_contraction:
                volume_score = 10
            else:
                volume_score = 0

            # --- 6. PRECISION ADDS (SCORING) ---
            precision_score = 0
            
            # A. Multi-Candle Confirmation (+10 pts)
            if is_short:
                bearish_entry = l_close_val < l_open_val
                if bearish_entry and no_strong_counter:
                    precision_score += 10
            else:
                bullish_entry = l_close_val > l_open_val
                if bullish_entry and no_strong_counter:
                    precision_score += 10
            
            # B. Wick Rejection (+10 pts)
            body_size = abs(l_close_val - l_open_val)
            if is_short:
                upper_wick = l_high_val - max(l_open_val, l_close_val)
                if upper_wick > body_size and upper_wick > (l_close_val * 0.0005):
                    precision_score += 10
            else:
                lower_wick = min(l_open_val, l_close_val) - l_low_val
                if lower_wick > body_size and lower_wick > (l_close_val * 0.0005):
                    precision_score += 10
            
            # C. Directional Micro-Consolidation (+10 pts) [V5.8]
            _last_3 = df.iloc[-4:-1]
            h3_val = float(_last_3['high'].max())
            l3_val = float(_last_3['low'].min())
            micro_cons_range = h3_val - l3_val
            
            if is_short:
                if (micro_cons_range / max(atr_val, 1e-6)) < 0.8 and l_close_val < ema9_val:
                    precision_score += 10
                
                # D. ATR-Normalized Momentum Continuation (+10 pts) [V5.4]
                candle_range = l_high_val - l_low_val
                candle_strength = (l_close_val - l_low_val) / candle_range if candle_range > 0 else 0.5
                momentum_strength_atr = (l_open_val - l_close_val) / max(atr_val, 1e-6)
                momentum_ok = (bearish_entry and candle_strength < 0.25 and momentum_strength_atr > 0.2)
                if momentum_ok:
                    precision_score += 10
            else:
                if (micro_cons_range / max(atr_val, 1e-6)) < 0.8 and l_close_val > ema9_val:
                    precision_score += 10
                
                # D. ATR-Normalized Momentum Continuation (+10 pts) [V5.4]
                candle_range = l_high_val - l_low_val
                candle_strength = (l_close_val - l_low_val) / candle_range if candle_range > 0 else 0.5
                momentum_strength_atr = (l_close_val - l_open_val) / max(atr_val, 1e-6)
                momentum_ok = (bullish_entry and candle_strength > 0.75 and momentum_strength_atr > 0.2)
                if momentum_ok:
                    precision_score += 10

            # --- 7. V6 EDGE LAYER FEATURES ---
            
            # 1. LIQUIDITY SWEEP (+15 pts) [V6.1 REFINE]
            swing_low_series = df['low'].iloc[-6:-1]
            swing_high_series = df['high'].iloc[-6:-1]
            swing_low = float(swing_low_series.min())
            swing_high = float(swing_high_series.max())
            
            if is_short:
                sweep_depth = (l_high_val - swing_high) / (swing_high if swing_high > 0 else 1)
                liquidity_sweep = (sweep_depth > 0.001) and (l_close_val < swing_high)
            else:
                sweep_depth = (swing_low - l_low_val) / (swing_low if swing_low > 0 else 1)
                liquidity_sweep = (sweep_depth > 0.001) and (l_close_val > swing_low)
                
            sweep_score = 15 if liquidity_sweep else 0
            
            # 2. EMA RECLAIM STRENGTH (+10 pts) [V6.2 REFINE]
            prev_ema9 = float(ema9_series.iloc[-2])
            
            if is_short:
                momentum_atr = (l_open_val - l_close_val) / max(atr_val, 1e-6)
                ema_reclaim = (p_close_val > prev_ema9) and (l_close_val < ema9_val) and (c_strength < 0.3) and (momentum_atr > 0.15)
            else:
                momentum_atr = (l_close_val - l_open_val) / max(atr_val, 1e-6)
                ema_reclaim = (p_close_val < prev_ema9) and (l_close_val > ema9_val) and (c_strength > 0.7) and (momentum_atr > 0.15)
                
            ema_reclaim_score = 10 if ema_reclaim else 0
            
            # 3. TIME COMPRESSION (ENERGY BUILD-UP) (+10 pts) [V6.3 REFINE]
            # Detect energy coiling BELOW EMA9 for Shorts, ABOVE EMA9 for Longs
            last_5_df = df.tail(5)
            avg_range = (last_5_df['high'] - last_5_df['low']).mean()
            if is_short:
                compression = (avg_range < (0.7 * atr_val)) and (l_high_val < ema9_val)
            else:
                compression = (avg_range < (0.7 * atr_val)) and (l_low_val > ema9_val)
                
            compression_score = 10 if compression else 0
            
            # 4. ENTRY ZONE QUALITY FILTER [V6.4 REFINE]
            # Adaptive proximity bonus/penalty using ATR (volatility parity)
            entry_distance_atr = abs(l_close_val - breakout_level) / max(atr_val, 1e-6)
            entry_zone_score = 0
            if entry_distance_atr < 0.5: # Within 0.5 ATR
                entry_zone_score = 10
            elif entry_distance_atr > 1.5: # Beyond 1.5 ATR (Chasing)
                entry_zone_score = -10

            # --- 8. VALIDATION LAYER (PENALTIES) ---
            validation_penalty = 0
            
            # 1. ADAPTIVE OVEREXTENSION [V5.9]
            dist_from_break_atr = (l_close_val - breakout_level) / max(atr_val, 1e-6)
            overextended = dist_from_break_atr > 1.5
            if overextended: validation_penalty += 15
            
            # 2. BREAKOUT/BREAKDOWN CONTINUITY CHECK (Penalty -20 pts) [V6.5 REFINE]
            if is_short:
                breakout_failure = (l_close_val > breakout_level * 1.002) and (c_strength > 0.6)
            else:
                breakout_failure = (l_close_val < breakout_level * 0.998) and (c_strength < 0.4)
                
            if breakout_failure: validation_penalty += 20
            
            # 3. RESISTANCE / SUPPORT FILTER [V5.6]
            if is_short:
                recent_20_lows = df['low'].iloc[-21:-1]
                recent_low = float(recent_20_lows.min())
                breakdown_confirmed = l_close_val < (recent_low * 0.998)
                support_risk = (not breakdown_confirmed and l_close_val >= recent_low and (l_close_val - recent_low) / (recent_low if recent_low > 0 else 1) < 0.003)
                if support_risk: validation_penalty += 10
            else:
                recent_20_highs = df['high'].iloc[-21:-1]
                recent_high = float(recent_20_highs.max())
                breakout_confirmed = l_close_val > (recent_high * 1.002)
                resistance_risk = (not breakout_confirmed and l_close_val <= recent_high and (recent_high - l_close_val) / (recent_high if recent_high > 0 else 1) < 0.003)
                if resistance_risk: validation_penalty += 10
            
            # 4. VOLUME Sensitivity [V5.3]
            volume_dry_up = v3_avg < (v10_avg * 0.8)
            if volume_dry_up: validation_penalty += 10
            
            # 5. STRUCTURAL TOLERANCE (0.2%) [V5.10]
            if is_short:
                prev_5_highs = df['high'].iloc[-6:-1]
                p5_high_val = float(prev_5_highs.max())
                structure_break = (l_high_val - p5_high_val) / (p5_high_val if p5_high_val > 0 else 1)
                structure_weak = (structure_break > 0.002) and (l_close_val >= p5_high_val)
            else:
                prev_5_lows = df['low'].iloc[-6:-1]
                p5_low_val = float(prev_5_lows.min())
                structure_break = (p5_low_val - l_low_val) / (p5_low_val if p5_low_val > 0 else 1)
                structure_weak = (structure_break > 0.002) and (l_close_val <= p5_low_val)
                
            if structure_weak: validation_penalty += 20

            # --- 9. FINAL SCORING ---
            # V16.1: Harmonized Trend Bypass (Smart Gate)
            # Apply a heavy "Trend Gravity" penalty for trades in the negative/bearish range
            # UNLESS a Smart Gate (Reclaim/Div) is active, in which case we cut the penalty.
            smart_gate = context.get("smart_gate", False) if context else False
            
            trend_penalty = 0
            if not trend_hold:
                if smart_gate:
                    trend_penalty = 15 # Reduced penalty for high-conviction reclaims
                else:
                    trend_penalty = 50 # Standard hard penalty for falling knives
            
            base_score = (pullback_score + trend_score + trigger_score + volume_score + 
                         precision_score + sweep_score + ema_reclaim_score + compression_score + entry_zone_score)
            
            # Enforce a hard ceiling and floor to prevent "Glitch Scores" (Phase 103)
            # Mathematical maximum before clamping is ~185, we sanitize this for the UI/Signals
            entry_score = max(0, min(base_score - validation_penalty - trend_penalty, 100))
            
            entry_quality = "Avoid"
            if entry_score >= 90: entry_quality = "A+"
            elif entry_score >= 75: entry_quality = "A"
            elif entry_score >= 60: entry_quality = "B"

            # --- 10. LIQUIDITY WINDOWS [V5.11] ---
            from datetime import time
            
            valid_time = True
            if isinstance(df.index, pd.DatetimeIndex):
                c_time = df.index[-1].time()
                valid_time = ((time(9, 15) <= c_time <= time(11, 30)) or (time(13, 45) <= c_time <= time(15, 15)))

            # --- 11. RISK MANAGEMENT ENGINE (V6.0) ---
            # 1. Dual Stop Loss: Selects the tighter floor
            if is_short:
                atr_sl = l_close_val + (atr_val * 1.0)
                structural_sl = float(df['high'].iloc[-6:].max())
                stop_loss = min(atr_sl, structural_sl) # Lower price = tighter SL for shorts
                sl_distance = stop_loss - l_close_val
            else:
                atr_sl = l_close_val - (atr_val * 1.0)
                structural_sl = float(df['low'].iloc[-6:].min())  # Previous 5 lows + current candle
                stop_loss = max(atr_sl, structural_sl) # Higher price = tighter SL for longs
                sl_distance = l_close_val - stop_loss
            sl_pct = sl_distance / (l_close_val if l_close_val > 0 else 1)
            
            # FIX N1: Removed hardcoded capital=10000. Position sizing is user-specific.
            # This value is a reference/example only — real deployment must use per-user capital config.
            # risk_amount and position_size are still calculated for reference in the UI.
            capital = 10000  # REFERENCE ONLY: Replace with user's actual capital at integration layer
            risk_amount = capital * 0.01  # 1% risk rule
            position_size = int(risk_amount / sl_distance) if sl_distance > 0 else 0
            
            # 3. Multi-Target Strategy (RR)
            if is_short:
                target_1 = l_close_val - (sl_distance * 1.0)
                target_2 = l_close_val - (sl_distance * 2.0)
                rr_ratio = (l_close_val - target_2) / (sl_distance if sl_distance > 0 else 1)
            else:
                target_1 = l_close_val + (sl_distance * 1.0) # 1R (Partial target)
                target_2 = l_close_val + (sl_distance * 2.0) # 2R (Main trend target)
                rr_ratio = (target_2 - l_close_val) / (sl_distance if sl_distance > 0 else 1)
            
            # 4. Risk Filters
            # FIX VOLATILITY CAPPING: Increased SL threshold so explosive ATR trades aren't automatically blocked.
            # The position sizing naturally protects capital by buying fewer shares on wide stops.
            trade_valid = (sl_pct <= 0.045) and (rr_ratio >= 1.5) # Max 4.5% SL, Min 1.5 RR

            # Final Decision: Threshold 70 [V6]
            is_entry = (
                (entry_score >= 70) and 
                reversal_trigger and 
                (not overextended) and 
                (not breakout_failure) and 
                (not structure_weak) and 
                valid_time and 
                trade_valid
            )

            risk_level = "High"
            if entry_score >= 80 and sl_pct <= 0.01: risk_level = "Low"
            elif entry_score >= 60 and sl_pct <= 0.015: risk_level = "Medium"

            return {
                "is_entry": is_entry,
                "entry_score": round(entry_score, 1),
                "entry_quality": entry_quality,
                "risk_level": risk_level,
                
                "entry_price": float(l_close_val),
                "stop_loss": round(stop_loss, 2),
                "target_1": round(target_1, 2),
                "target_2": round(target_2, 2),
                "position_size": position_size,
                
                "signals": {
                    "liquidity_sweep": liquidity_sweep,
                    "ema_reclaim": ema_reclaim,
                    "compression": compression,
                    "volume_profile": "High Conviction" if vol_ratio >= 1.5 else "Standard",
                    
                    "breakout_failure": breakout_failure,
                    "structure_weak": structure_weak,
                    "trade_valid": trade_valid,
                    "rr_ratio": round(rr_ratio, 2)
                }
            }
        except Exception as e:
            print(f"Error in Pullback Engine for {df.attrs.get('symbol', 'Unknown')}: {e}")
            import traceback
            traceback.print_exc()
            return {
                "is_entry": False, "entry_score": 0, "entry_quality": "Avoid", "risk_level": "High",
                "entry_price": 0.0, "stop_loss": 0.0, "target_1": 0.0, "target_2": 0.0, "position_size": 0,
                "signals": {}
            }

    @staticmethod
    def detect_smart_money_accumulation(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if len(df) < 30: return {"accumulation_detected": False}

            latest = df.iloc[-1]
            # --- 1. CONSOLIDATION DETECTION ---
            # Using last 20 candles
            last_20 = df.tail(20)
            
            _high_all = last_20['high']
            h_s = _high_all.iloc[:, 0] if isinstance(_high_all, pd.DataFrame) else _high_all
            _low_all = last_20['low']
            l_s = _low_all.iloc[:, 0] if isinstance(_low_all, pd.DataFrame) else _low_all
            _vol_all = last_20['volume']
            v_s = _vol_all.iloc[:, 0] if isinstance(_vol_all, pd.DataFrame) else _vol_all
            
            highest_high = float(h_s.max())
            lowest_low = float(l_s.min())
            
            _l_close = latest['close']
            current_price = safe_scalar(_l_close)
            
            range_pct = (highest_high - lowest_low) / (current_price if current_price > 0 else 1) * 100
            
            # Price above or near VWAP check
            vwap_series = IntradayTechnicalAnalysis.calculate_vwap_series(df)
            _vwap_val = vwap_series.iloc[-1] if not vwap_series.empty else 0.0
            vwap_now = safe_scalar(_vwap_val)
            
            # price remains above or near VWAP (< 0.5% offset if below)
            price_near_vwap = current_price >= vwap_now * 0.995 
            
            consolidation_zone = (range_pct < 2.5) and price_near_vwap

            # --- 2. ACCUMULATION VOLUME PATTERN ---
            # Avg vol last 10 vs Avg vol previous 10 (10-20 ago)
            avg_vol_last_10 = float(v_s.tail(10).mean())
            avg_vol_prev_10 = float(v_s.iloc[0:10].mean())
            
            volume_acc_ratio = avg_vol_last_10 / (avg_vol_prev_10 if avg_vol_prev_10 > 0 else 1)
            volume_accumulation = volume_acc_ratio > 1.25

            # --- 3. SHALLOW PULLBACK DETECTION ---
            # Pullbacks remain within 1.5%-2% range
            # Lows are gradually rising (Low[-1] > Low[-10])
            pullbacks_shallow = True
            for i in range(-5, 0):
                # pullback from local 20-candle high
                _curr_low = l_s.iloc[i]
                curr_low_val = safe_scalar(_curr_low)
                pb = (highest_high - curr_low_val) / (highest_high if highest_high > 0 else 1) * 100
                if pb > 2.0:
                    pullbacks_shallow = False
                    break
            
            _l_low_scalar = l_s.iloc[-1]
            l_low_val = safe_scalar(_l_low_scalar)
            
            _prev_low_10_scalar = l_s.iloc[-10]
            prev_low_10_val = safe_scalar(_prev_low_10_scalar)
            higher_lows = l_low_val > prev_low_10_val
            higher_lows_pattern = pullbacks_shallow and higher_lows

            # --- 4. VWAP SUPPORT CHECK ---
            # Price touches VWAP multiple times and rebounds above
            touches = 0
            _close_all = df['close']
            c_s_full = _close_all.iloc[:, 0] if isinstance(_close_all, pd.DataFrame) else _close_all
            _low_all_full = df['low']
            l_s_full = _low_all_full.iloc[:, 0] if isinstance(_low_all_full, pd.DataFrame) else _low_all_full
            
            for i in range(-20, 0):
                # Touch = low near vwap, Rebound = close above vwap
                _vi = vwap_series.iloc[i]
                vi_val = safe_scalar(_vi)
                _ci = c_s_full.iloc[i]
                ci_val = safe_scalar(_ci)
                _li = l_s_full.iloc[i]
                li_val = safe_scalar(_li)
                
                if li_val <= vi_val * 1.002 and ci_val > vi_val:
                    touches += 1
            
            vwap_accumulation_support = touches >= 2

            # V6.1: Accumulation must last minimum 4 candles
            # We verify that consolidation was valid for at least 4 bars
            def is_consolidating(idx_offset):
                if idx_offset < 1: return False
                start = max(0, idx_offset - 20)
                slice_h = h_s.iloc[start:idx_offset] if hasattr(h_s, 'iloc') else h_s[start:idx_offset]
                slice_l = l_s.iloc[start:idx_offset] if hasattr(l_s, 'iloc') else l_s[start:idx_offset]
                slice_c = c_s_full.iloc[start:idx_offset] if hasattr(c_s_full, 'iloc') else c_s_full[start:idx_offset]
                
                if slice_h.empty: return False
                s_high = float(slice_h.max())
                s_low = float(slice_l.min())
                _lc = slice_c.iloc[-1] if not slice_c.empty else 0.0
                lc_val = safe_scalar(_lc)
                s_range = (s_high - s_low) / (lc_val if lc_val > 0 else 1) * 100
                return s_range < 2.5

            # FIX N2 & V2: Overhauled logic to strictly prevent false positives
            duration_validation = False
            try:
                if len(df) >= 4:
                    duration_validation = all([is_consolidating(i) for i in range(len(df), max(0, len(df)-4), -1)])
            except Exception:
                duration_validation = False  # DO NOT default to True on error

            # --- 5. ACCUMULATION CONFIRMATION (V3.8 Weighted Scoring) ---
            accumulation_score = 0
            
            # Condition 1: Consolidation Zone (20 pts)
            if consolidation_zone: accumulation_score += 20
            
            # Condition 2: Volume Accumulation (20 pts)
            if volume_accumulation: accumulation_score += 20
            
            # Condition 3: Higher Lows Pattern (15 pts)
            if higher_lows_pattern: accumulation_score += 15
            
            # Condition 4: VWAP Support (15 pts)
            if vwap_accumulation_support: accumulation_score += 15
            
            # Condition 5: Duration Validation (10 pts)
            if duration_validation: accumulation_score += 10
            
            # --- 6. LIQUIDITY SWEEP ENHANCEMENT (20 pts) ---
            sweep_ctx = IntradayTechnicalAnalysis.detect_liquidity_sweep_enhanced(df)
            if sweep_ctx["is_sweep"]: 
                accumulation_score += 20

            # --- 7. TREND FILTER (EMA 20) ---
            ema_20_series = EMAIndicator(close=df['close'], window=20).ema_indicator()
            _e20 = ema_20_series.iloc[-1] if not ema_20_series.empty else 0.0
            ema_20_val = safe_scalar(_e20)
            trend_ok = current_price > ema_20_val

            # Confidence Level Mapping
            if accumulation_score >= 80:
                confidence_level = "High Confidence Accumulation"
            elif accumulation_score >= 60:
                confidence_level = "Moderate Accumulation"
            elif accumulation_score >= 40:
                confidence_level = "Weak Setup"
            else:
                confidence_level = "No Accumulation"

            # Final Engine Decision: Score 60+ AND Trend must be Bullish
            accumulation_detected = (accumulation_score >= 60) and trend_ok

            # --- 8. BREAKOUT ENGINE V4.0 ---
            breakout_ctx = IntradayTechnicalAnalysis.detect_breakout_engine_v4(
                df, 
                consolidation_high=highest_high, 
                vwap=vwap_now, 
                sweep_ctx=sweep_ctx
            )
            
            is_breakdown = current_price < lowest_low

            return {
                "accumulation_detected": accumulation_detected,
                "accumulation_score": accumulation_score,
                "confidence_level": confidence_level,
                "trend_ok": trend_ok,
                "is_sweep_confirmed": sweep_ctx["is_sweep"],
                "sweep_range_low": sweep_ctx["range_low"],
                "sweep_vol_spike": sweep_ctx["volume_spike"],
                "sweep_score": sweep_ctx.get("sweep_score", 0),
                "consolidation_range_percent": round(range_pct, 2),
                "volume_accumulation_ratio": round(volume_acc_ratio, 2),
                "avg_vol_consolidation": float(v_s.mean()),
                "consolidation_high": float(highest_high),
                "consolidation_low": float(lowest_low),
                "is_breakout": breakout_ctx["is_breakout"],
                "breakout_score": breakout_ctx["breakout_score"],
                "breakout_intensity": breakout_ctx["breakout_strength"],
                "breakout_details": breakout_ctx,
                "is_breakdown": is_breakdown,
                "pattern_label": confidence_level if accumulation_detected else "None"
            }
        except Exception as e:
            print(f"Error in Accumulation Detection: {e}")
            return {"accumulation_detected": False}

    @staticmethod
    def check_ema_stack(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if len(df) < 20: return {"is_aligned": False, "ema20_slope_up": False}

            _close = df['close']
            close_series = _close.iloc[:, 0] if isinstance(_close, pd.DataFrame) else _close
            ema_9 = EMAIndicator(close=close_series, window=9).ema_indicator()
            ema_20 = EMAIndicator(close=close_series, window=20).ema_indicator()
            _l_close = df['close'].iloc[-1]
            close_now = safe_scalar(_l_close)
            ema_9_now = safe_scalar(ema_9.iloc[-1])
            ema_20_now = safe_scalar(ema_20.iloc[-1])
            ema_20_prev = ema_20.iloc[-2]
            
            # Ensure EMAs are scalars too (some libraries might return Series if input was duplicate)
            ema_9_now = safe_scalar(ema_9_now)
            ema_20_now = safe_scalar(ema_20_now)
            ema_20_prev = safe_scalar(ema_20_prev)

            price_above = close_now > ema_9_now
            ema_9_above = ema_9_now > ema_20_now
            ema20_slope_up = ema_20_now > ema_20_prev

            is_aligned = price_above and ema_9_above and ema20_slope_up

            return {
                "is_aligned": is_aligned,
                "ema20_slope_up": ema20_slope_up,
                "ema_9": round(ema_9_now, 2),
                "ema_20": round(ema_20_now, 2)
            }
        except:
            return {"is_aligned": False, "ema20_slope_up": False}

    @staticmethod
    def calculate_value_area(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {"poc": 0.0, "vah": 0.0, "val": 0.0}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if isinstance(df.index, pd.DatetimeIndex):
                current_date = df.index[-1].date()
                today_df = df[df.index.date == current_date]
            else:
                today_df = df.tail(75) # Fallback for non-timed data
            
            if today_df.empty: 
                bp = float(df['close'].iloc[-1])
                return {"poc": bp, "vah": bp, "val": bp}
            
            # Use 50 bins for the price range of the day
            min_p = today_df['low'].min()
            max_p = today_df['high'].max()
            if min_p == max_p: 
                return {"poc": min_p, "vah": min_p, "val": min_p}
            
            bins = np.linspace(min_p, max_p, 51)
            # Assignment to bins based on candle high/low/close average
            _high = today_df['high']
            _low = today_df['low']
            _close = today_df['close']
            h_s = _high.iloc[:, 0] if isinstance(_high, pd.DataFrame) else _high
            l_s = _low.iloc[:, 0] if isinstance(_low, pd.DataFrame) else _low
            c_s = _close.iloc[:, 0] if isinstance(_close, pd.DataFrame) else _close
            
            prices = (h_s + l_s + c_s) / 3
            _vol = today_df['volume']
            v_s = _vol.iloc[:, 0] if isinstance(_vol, pd.DataFrame) else _vol
            volume_profile, _ = np.histogram(prices, bins=bins, weights=v_s)
            
            total_vol = volume_profile.sum()
            sorted_bins = sorted(enumerate(volume_profile), key=lambda x: x[1], reverse=True)
            
            va_vol = 0
            va_indices = set()
            for idx, vol in sorted_bins:
                va_vol += vol
                va_indices.add(idx)
                if va_vol >= total_vol * 0.70:
                    break
                    
            vah = bins[max(va_indices) + 1] if max(va_indices) + 1 < len(bins) else bins[-1]
            val = bins[min(va_indices)]
            poc = (bins[sorted_bins[0][0]] + bins[sorted_bins[0][0] + 1]) / 2
            
            return {"poc": float(poc), "vah": float(vah), "val": float(val)}
        except:
            bp = float(df['close'].iloc[-1])
            return {"poc": bp, "vah": bp, "val": bp}

    @staticmethod
    def detect_poc_bounce(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if len(df) < 20: return {"is_bounce": False, "is_vah_rejection": False, "is_val_bounce": False}
            
            va = IntradayTechnicalAnalysis.calculate_value_area(df)
            poc = va["poc"]
            vah = va["vah"]
            val = va["val"]
            latest = df.iloc[-1]
            
            # 1. Test of POC
            _l_low = latest['low']
            l_low_val = safe_scalar(_l_low)
            _l_high = latest['high']
            l_high_val = safe_scalar(_l_high)
            near_poc = l_low_val <= poc * 1.002 and l_high_val >= poc * 0.998
            near_val = l_low_val <= val * 1.002 and l_high_val >= val * 0.998
            near_vah = l_high_val >= vah * 0.998 and l_low_val <= vah * 1.002
            
            # 2. Bullish Confirmation
            _l_close = latest['close']
            l_close_val = safe_scalar(_l_close)
            _l_open = latest['open']
            l_open_val = safe_scalar(_l_open)
            is_bullish = l_close_val > l_open_val
            is_bearish = l_close_val < l_open_val
            
            # 3. High Volume
            _vol_all = df['volume']
            vol_series = _vol_all.iloc[:, 0] if isinstance(_vol_all, pd.DataFrame) else _vol_all
            _vol_ma_res = vol_series.rolling(20).mean().iloc[-1]
            vol_ma = safe_scalar(_vol_ma_res)
            
            _l_vol = latest['volume']
            l_vol_val = safe_scalar(_l_vol)
            high_vol = l_vol_val > vol_ma
            
            setup_detected = near_poc and is_bullish and high_vol
            val_bounce = near_val and is_bullish and high_vol
            vah_rejection = near_vah and is_bearish
            
            return {
                "is_bounce": setup_detected,
                "is_val_bounce": val_bounce,
                "is_vah_rejection": vah_rejection,
                "poc_val": poc,
                "vah_val": vah,
                "val_val": val
            }
        except:
            return {"is_bounce": False, "is_vah_rejection": False, "is_val_bounce": False}

    @staticmethod
    def calculate_cvd_proxy(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        try:
            if not isinstance(df.index, pd.DatetimeIndex): return {"cvd": 0, "status": "Neutral", "score": 50}
            
            # Analyze only today's volume flow
            current_date = df.index[-1].date()
            today_df = df[df.index.date == current_date]
            
            if today_df.empty: return {"cvd": 0, "cvd_ratio": 0.0, "status": "Neutral", "score": 50}
            
            _cl = today_df['close']
            _op = today_df['open']
            _hi = today_df['high']
            _lo = today_df['low']
            _vl = today_df['volume']
            c_s = _cl.iloc[:, 0] if isinstance(_cl, pd.DataFrame) else _cl
            o_s = _op.iloc[:, 0] if isinstance(_op, pd.DataFrame) else _op
            h_s = _hi.iloc[:, 0] if isinstance(_hi, pd.DataFrame) else _hi
            l_s = _lo.iloc[:, 0] if isinstance(_lo, pd.DataFrame) else _lo
            v_s = _vl.iloc[:, 0] if isinstance(_vl, pd.DataFrame) else _vl
            
            # [V23 FIX #9] Proportional CVD — industry-standard candle delta approximation
            # OLD: Binary classification (entire candle vol = buy if close > open) missed distribution
            # NEW: Allocate volume proportionally based on close position within high-low range
            ranges = h_s - l_s
            ranges = ranges.replace(0, np.nan)  # Avoid div/0 on doji candles
            buy_fraction = (c_s - l_s) / ranges  # 0 = closed at low, 1 = closed at high
            buy_fraction = buy_fraction.fillna(0.5)  # Doji = 50/50 split
            
            buy_vol = (v_s * buy_fraction).sum()
            sell_vol = (v_s * (1 - buy_fraction)).sum()
            
            cvd = buy_vol - sell_vol
            total_vol = buy_vol + sell_vol
            
            if total_vol == 0: return {"cvd": 0, "cvd_ratio": 0.0, "status": "Neutral", "score": 50}
            
            cvd_ratio = cvd / total_vol
            
            # CVD Ratio: +1.0 means 100% buying volume, -1.0 means 100% selling volume
            if cvd_ratio > 0.3:
                status = "Strong Buy Accumulation"
                score = 100
            elif cvd_ratio > 0.1:
                status = "Mild Accumulation"
                score = 75
            elif cvd_ratio < -0.3:
                status = "Strong Distribution"
                score = 0
            elif cvd_ratio < -0.1:
                status = "Mild Distribution"
                score = 25
            else:
                status = "Balanced Flow"
                score = 50
                
            return {
                "cvd": round(cvd, 0),
                "cvd_ratio": round(cvd_ratio, 2),
                "status": status,
                "score": score
            }
        except Exception as _e:
            _ta_logger.warning(f"[calculate_cvd_proxy] {df.attrs.get('symbol','?')}: {_e}")
            return {"cvd": 0, "cvd_ratio": 0.0, "status": "Neutral", "score": 50}

    @staticmethod
    def analyze_stock(df: pd.DataFrame) -> dict:
        if df is None or df.empty: return {}
        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])
        if df.empty or len(df) < 20: return {}
        
        # Phase 97: Robust Column Cleansing (Fix for Ambiguous Series Truth Value)
        # Ensure we have single Series for each OHLCV column even if duplicates exist
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                series = df[col]
                if isinstance(series, pd.DataFrame):
                    df[col] = series.iloc[:, 0]
        
        latest = df.iloc[-1]
        
        # 1. VWAP (30% weight in engine) - Daily anchor is standard
        vwap_ctx = IntradayTechnicalAnalysis.analyze_vwap_advanced(df)
        
        # Ensure close and vwap are scalars (handle potential duplicate columns/Series)
        close = latest['close']
        vwap = vwap_ctx["vwap_val"]
        
        close_val = safe_scalar(close)
        vwap_val = safe_scalar(vwap)
        
        # STRICT VWAP: Must be > 0.2% above VWAP to be considered truly bullish and not just chopping around it
        vwap_score = 100 if vwap_val > 0 and close_val > vwap_val * 1.002 else (50 if vwap_val > 0 and close_val > vwap_val else 0)
        vwap_status = "Price > VWAP (Trend)" if vwap_score == 100 else ("Chopping at VWAP" if vwap_score == 50 else "Price < VWAP")
        
        # 2. Advanced Volume Analysis (V3.2: ADV20 & Same-Time RVOL)
        symbol = df.attrs.get("symbol", "UNKNOWN")
        liq_ctx = liquidity_service.get_liquidity(symbol)
        adv20 = liq_ctx.get("adv20", 0)
        liq_level = liq_ctx.get("level", "Unknown")
        
        # Calculate Same-Time RVOL
        current_dt = df.index[-1]
        current_time = current_dt.strftime("%H:%M")
        avg_vol_at_time = liquidity_service.get_benchmark_vol(symbol, current_time)
        
        current_vol_raw = latest['volume']
        current_vol = safe_scalar(current_vol_raw)
        rvol_time_reference = current_time
        
        if avg_vol_at_time > 0:
            rvol = current_vol / max(avg_vol_at_time, 1e-6)
        else:
            # FIX #6: Dynamic RVOL Divisor (Timeframe-Aware)
            # OLD: Fixed divisor of 25, assumed 15min interval = 375min/15 = 25 candles
            # Issue: On 5min data, there are 75 candles, making volume look 3x higher than reality
            # NEW: Infer the interval from the data spacing and calculate the correct divisor
            if isinstance(df.index, pd.DatetimeIndex) and len(df.index) >= 2:
                inferred_mins = (df.index[-1] - df.index[-2]).total_seconds() / 60
                # Guard against anomalies (e.g. gaps from circuit breaks)
                if 1 <= inferred_mins <= 60:
                    session_minutes = 375  # NSE session: 9:15am to 3:30pm
                    candles_per_session = max(1, int(session_minutes / inferred_mins))
                else:
                    candles_per_session = 25  # Fallback if inference fails
            else:
                candles_per_session = 25  # Static fallback
            
            avg_candle_vol_raw = adv20 / candles_per_session if adv20 > 0 else df['volume'].rolling(20).mean().iloc[-1]
            avg_candle_vol = safe_scalar(avg_candle_vol_raw)
            rvol = current_vol / max(avg_candle_vol, 1e-6)
            rvol_time_reference = "ADV25_FALLBACK"
            
        cvd_ctx = IntradayTechnicalAnalysis.calculate_cvd_proxy(df)
        
        # RVOL Score Mapping
        if rvol > 2.5: rvol_score = 100 # Institutional
        elif rvol > 1.5: rvol_score = 80 # Strong
        elif rvol > 1.0: rvol_score = 60 # Normal(+)
        else: rvol_score = 40 # Normal/Low
        
        # Participatory Decay
        if rvol < 0.5:
            rvol_score = min(30, rvol_score)
        
        # 3. EMA 9 & 20 (10% weight in engine)
        ema_9_series = EMAIndicator(close=df['close'], window=9).ema_indicator()
        ema_20_series = EMAIndicator(close=df['close'], window=20).ema_indicator()
        ema_9 = ema_9_series.iloc[-1]
        ema_20 = ema_20_series.iloc[-1]
        # FIX #5: Use close_val (scalar) for all comparisons to avoid 'Ambiguous truth value'
        # Raw `close` from latest['close'] may still be a Series on duplicate-column data
        ema_score = 0
        ema_status = "Bearish"
        if ema_9 > ema_20 and close_val > ema_9:
            ema_score = 100
            ema_status = "Strong Bullish (> 9EMA > 20EMA)"
        elif ema_9 > ema_20:
            ema_score = 75
            ema_status = "Bullish Cross"
        elif close_val > ema_20:
            ema_score = 50
            ema_status = "Holding 20EMA"
            
        # 4. Pivot Points (15% weight in engine) - Daily timeframe
        pivots = IntradayTechnicalAnalysis.calculate_pivots(df)
        pivot_score = 50
        pivot_status = "Between Levels"
        res_1 = pivots.get("R1", close_val * 1.05)
        sup_1 = pivots.get("S1", close_val * 0.95)
        
        if close_val > res_1:
            pivot_score = 100  # Clean Breakout
            pivot_status = "Above R1 Breakout"
        elif close_val < sup_1:
            pivot_score = 0
            pivot_status = "Below S1 Breakdown"
        elif close_val > pivots.get("P", 0):
            pivot_score = 75
            pivot_status = "Above Central Pivot"
            
        # 5. Price Action / Order Flow Proxy (20% weight in engine)
        # Replacing Level 2 with candle structure: Strong close near high + volume
        candle_range = latest['high'] - latest['low']
        close_relative = (close_val - latest['low']) / candle_range if candle_range > 0 else 0.5
        
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
            "Volume": {"score": rvol_score, "details": [
                {"text": f"Flow: {cvd_ctx['status']}", "type": "positive" if cvd_ctx["score"] > 50 else "negative" if cvd_ctx["score"] < 50 else "neutral", "label": "CVD", "value": f"{cvd_ctx['cvd_ratio']*100:+.0f}%"},
                {"text": "Relative Volume", "type": "positive" if rvol >= 1.5 else "neutral", "label": "RVOL", "value": f"{round(rvol,2)}x"}
            ]},
            "Price Action": {"score": pa_score, "details": [{"text": "Order Flow Proxy", "type": "positive" if pa_score > 50 else "negative", "label": "ACTION", "value": pa_status}]},
            "Trend": {"score": ema_score, "details": [{"text": "9/20 EMA", "type": "positive" if ema_score > 50 else "negative", "label": "EMA", "value": ema_status}]},
            "Risk & Levels": {"score": pivot_score, "details": [{"text": "Pivot Defense", "type": "positive" if pivot_score > 50 else "negative", "label": "PIVOT", "value": pivot_status}]}
        }
        
        # 6. MFI (Money Flow Index) Confirmation
        try:
            mfi = MFIIndicator(high=df['high'], low=df['low'], close=df['close'], volume=df['volume'], window=14).money_flow_index().iloc[-1]
            groups["Volume"]["details"].append({
                "text": "Institutional Flow (MFI)",
                "type": "positive" if mfi > 60 else "negative" if mfi < 40 else "neutral",
                "label": "MFI",
                "value": round(mfi, 1)
            })
        except:
            pass

        # 7. ADX (Trend Strength) - Professional Filter
        adx_ctx = IntradayTechnicalAnalysis.calculate_adx(df)
        groups["Trend"]["details"].append({
            "text": f"ADX: {adx_ctx['status']}",
            "type": "positive" if adx_ctx['adx'] > 25 else "neutral",
            "label": "ADX",
            "value": f"{adx_ctx['adx']} ({adx_ctx['bias']})"
        })

        # 8. EMA Fan Bonus
        fan_ctx = IntradayTechnicalAnalysis.check_ema_fan(df)
        if fan_ctx["is_aligned"]:
            groups["Trend"]["details"].append({
                "text": "EMA Multi-Alignment",
                "type": "positive" if "Bullish" in fan_ctx["status"] else "negative",
                "label": "FAN",
                "value": fan_ctx["status"]
            })

        # 8. Adaptive Risk Management (Volatility-Adjusted)
        atr_series = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
        atr_val = atr_series.iloc[-1] if not atr_series.empty else 0.0
        # R4-3 FIX: Use close_val (scalar) not raw close for ATR fallback
        if pd.isna(atr_val) or atr_val == 0: atr_val = close_val * 0.015
        
        # Base multipliers
        sl_mult = 1.5
        tp_mult = 2.5
        is_trailing = False
        
        # Adapt to Parabolic Trend (ADX > 35)
        # STRICT RISK MANAGEMENT: Don't set SL too tight or you get wicked. Let winners run massively.
        if adx_ctx['adx'] > 35:
            sl_mult = 1.8 # Allow for slightly deeper pullbacks on aggressive runs
            tp_mult = 5.0 # Let winners run extremely far
            is_trailing = True
        elif adx_ctx['adx'] < 20: 
            # Choppy market: tighter targets, wider stops to avoid getting wicked out
            sl_mult = 2.0 
            tp_mult = 1.5 
            
        sl_dist = sl_mult * atr_val
        tp_dist = tp_mult * atr_val
        
        # Dynamic Support/Resistance relative to CURRENT price
        valid_res = [v for k, v in pivots.items() if v > close_val]
        nearest_pivot = min(valid_res) if valid_res else close_val + tp_dist
        target = max(nearest_pivot, close_val + tp_dist)
        
        valid_sup = [v for k, v in pivots.items() if v < close_val]
        best_sup = max(valid_sup) if (valid_sup and max(valid_sup) < close_val * 0.998) else close_val - sl_dist
        
        # Trailing stops use the ATR distance solely, ignoring pivots if it's parabolic
        if is_trailing:
            stop_loss = close_val - sl_dist
        else:
            stop_loss = max(best_sup, close_val - sl_dist)
        
        # Hard limits (Fix for Penny Stocks where ATR < 0.01)
        # Ensure a minimum 0.5% move for target and 0.4% move for stop loss to prevent overlaps
        min_target_dist = max(1.5 * sl_dist, close_val * 0.005)
        min_stop_dist = max(sl_dist, close_val * 0.004)
        
        if target <= close_val: target = close_val + min_target_dist
        if stop_loss >= close_val: stop_loss = close_val - min_stop_dist
        
        # Absolute safeguard against equal values due to rounding on micro-caps
        if round(target, 2) <= round(close_val, 2): target = close_val * 1.01
        if round(stop_loss, 2) >= round(close_val, 2): stop_loss = close_val * 0.99
        
        target_reason = "Technical Resistance Area" if valid_res and not is_trailing else "ATR Momentum Extension"
        
        # Special Bonus Events (Still mapped for the Engine to view)
        orb = IntradayTechnicalAnalysis.detect_orb(df)
        gap = IntradayTechnicalAnalysis.analyze_gap(df)
        # R4-2 FIX: Pass close_val (scalar) not raw close (potential Series) to sub-functions
        exhaustion = IntradayTechnicalAnalysis.check_exhaustion(df, close_val)
        pullback = IntradayTechnicalAnalysis.identify_pullback(df, close_val)
        squeeze = IntradayTechnicalAnalysis.detect_squeeze(df)
        divergence = IntradayTechnicalAnalysis.detect_rsi_divergence(df)
        trap = IntradayTechnicalAnalysis.detect_liquidity_trap(df)
        sweep = IntradayTechnicalAnalysis.detect_stop_hunt_sweep(df)
        poc_bounce = IntradayTechnicalAnalysis.detect_poc_bounce(df)
        
        # Anti-Chasing: Distance from ideal entry (VWAP or Pivot)
        best_entry = vwap if vwap_score == 100 else pivots.get("P", close_val)
        chase_dist = (close_val - best_entry) / max(atr_val, 1e-6)
        
        # STRICT CHASE: If ADX isn't soaring, chasing > 1.0 ATR is highly dangerous.
        chase_threshold = 1.6 if is_trailing else 1.0
        is_chasing = chase_dist > chase_threshold 
        
        ladder = IntradayTechnicalAnalysis.calculate_ladder(df, close_val)
        
        return {
            "vwap_score": vwap_score,
            "vwap_ctx": vwap_ctx,
            "rvol_score": rvol_score,
            "ema_score": ema_score,
            "pivot_score": pivot_score,
            "pa_score": pa_score,
            "adx_score": adx_ctx["score"],
            "adx_details": adx_ctx,
            "fan_bonus": fan_ctx["score_bonus"],
            "vwap_val": vwap,
            "pivot_val": pivots.get("P", 0),
            "rvol_val": rvol,
            "rvol_time_reference": rvol_time_reference,
            "adv20": adv20,
            "liq_level": liq_level,
            "groups": groups,
            "is_bullish_trend": ema_score >= 50 and vwap_score == 100,
            "trend": "BULLISH" if ema_score > 50 else "BEARISH" if ema_score < 50 else "NEUTRAL",
            "support": round(stop_loss, 2),
            "resistance": round(target, 2),
            "levels": ladder,
            "target_reason": "Trailing Stop Advised" if is_trailing else target_reason,
            "atr": atr_val,
            "is_trailing_stop": is_trailing,
            "orb": orb,
            "gap": gap,
            "exhaustion": exhaustion,
            "pullback": pullback,
            "squeeze": squeeze,
            "divergence": divergence,
            "trap": trap,
            "sweep": sweep,
            "poc_bounce": poc_bounce,
            "ema9": safe_scalar(ema_9),
            "ema9_prev": safe_scalar(ema_9_series.iloc[-2] if len(ema_9_series) > 1 else ema_9),
            "ema20": safe_scalar(ema_20),
            "ema20_prev": safe_scalar(ema_20_series.iloc[-2] if len(ema_20_series) > 1 else ema_20),
            # FIX #7: Removed duplicate keys (pa_score, adx_score, vwap_score)
            # that were already set at Lines 2191-2192/2186
            "trap_range_expansion": trap.get("trap_range_expansion", False),
            "chase": {
                "is_chasing": is_chasing,
                "dist_atr": round(chase_dist, 2)
            },
            "last_candle": {
                "h": float(latest['high']),
                "l": float(latest['low']),
                "c": float(latest['close']),
                "o": float(latest['open'])
            }
        }

    # [V34 GAP#1 FIX] Moved inside class body as proper @staticmethod
    # OLD: Defined at module level with @staticmethod decorator (no-op outside class),
    #      then monkey-patched back via IntradayTechnicalAnalysis.calculate_macd_histogram = ...
    # NEW: Native class method — no fragile monkey-patching needed
    @staticmethod
    def calculate_macd_histogram(df) -> dict:
        """[V32 P2] MACD Histogram direction for 15m momentum confirmation."""
        try:
            if df is None or df.empty or len(df) < 30:
                return {}
            from ta.trend import MACD
            close = df['close']
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            macd_ind = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
            hist = macd_ind.macd_diff()
            if len(hist) < 3:
                return {}
            h_now = float(hist.iloc[-1])
            h_prev = float(hist.iloc[-2])
            return {
                "histogram": h_now,
                "histogram_prev": h_prev,
                "histogram_rising": h_now > h_prev,
                "histogram_falling": h_now < h_prev,
                "zero_cross_bullish": h_prev < 0 and h_now > 0,
            }
        except Exception:
            return {}

ta_intraday = IntradayTechnicalAnalysis()

# Module Level Exports
analyze_stock = IntradayTechnicalAnalysis.analyze_stock
detect_pullback_entry_v45 = IntradayTechnicalAnalysis.detect_pullback_entry_v45
detect_micro_trend = IntradayTechnicalAnalysis.detect_micro_trend
