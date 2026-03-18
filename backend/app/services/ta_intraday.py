import pandas as pd
import numpy as np
from ta.volume import MFIIndicator
from ta.trend import ADXIndicator, EMAIndicator
from ta.volatility import AverageTrueRange
from app.services.liquidity_service import liquidity_service

class IntradayTechnicalAnalysis:
    
    @staticmethod
    def calculate_vwap_series(df: pd.DataFrame) -> pd.Series:
        """Calculates Volume Weighted Average Price (VWAP) as a series."""
        try:
            if isinstance(df.index, pd.DatetimeIndex):
                current_date = df.index[-1].date()
                today_df = df[df.index.date == current_date].copy()
            else:
                today_df = df.tail(75).copy()
            
            if today_df.empty: return pd.Series([df['close'].iloc[-1]] * len(df), index=df.index)
            
            tp = (today_df['high'] + today_df['low'] + today_df['close']) / 3
            vwap = (tp * today_df['volume']).cumsum() / today_df['volume'].cumsum()
            # Align with full df index
            return vwap.reindex(df.index).ffill()
        except:
            return pd.Series([df['close'].iloc[-1]] * len(df), index=df.index)

    @staticmethod
    def calculate_vwap(df: pd.DataFrame) -> float:
        """Calculates Volume Weighted Average Price (VWAP) - returns latest value."""
        vwap_s = IntradayTechnicalAnalysis.calculate_vwap_series(df)
        return float(vwap_s.iloc[-1])

    @staticmethod
    def analyze_vwap_advanced(df: pd.DataFrame) -> dict:
        """
        Advanced VWAP Analytics:
        - Slope calculation
        - High-volume reclaim detection
        - Oscillation/Chop detection
        """
        try:
            vwap_series = IntradayTechnicalAnalysis.calculate_vwap_series(df)
            
            # Ensure scalars (handle potential duplicate columns/Series)
            vwap_now = vwap_series.iloc[-1]
            vwap_now = float(vwap_now.iloc[0]) if hasattr(vwap_now, "iloc") else float(vwap_now)
            
            close_now = df['close'].iloc[-1]
            close_now = float(close_now.iloc[0]) if hasattr(close_now, "iloc") else float(close_now)
            
            # 1. Slope Calculation (Last 5 candles)
            lookback = 5
            if len(vwap_series) >= lookback:
                vwap_prev = vwap_series.iloc[-lookback]
                vwap_prev = float(vwap_prev.iloc[0]) if hasattr(vwap_prev, "iloc") else float(vwap_prev)
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
                "cross_count": crosses
            }
        except Exception as e:
            print(f"Error in advanced VWAP: {e}")
            return {"vwap_val": 0, "price_above": False, "slope_up": False, "reclaim": False, "oscillating": False}

    @staticmethod
    def detect_vwap_bullish_pullback(df: pd.DataFrame) -> dict:
        """
        Detects if price pulls back to VWAP and forms a bullish candle with high volume.
        Logic:
        1. Low <= VWAP * 1.0025 (Close enough to touch/test)
        2. Close > Open (Bullish)
        3. Volume > 20-period Average Volume
        """
        try:
            if len(df) < 20: return {"is_pullback_setup": False}
            
            vwap_series = IntradayTechnicalAnalysis.calculate_vwap_series(df)
            vwap_now = vwap_series.iloc[-1]
            latest = df.iloc[-1]
            
            # 1. Test of VWAP (Low is near or below VWAP)
            # We want to catch candles that 'bounce' off VWAP
            pullback_test = latest['low'] <= vwap_now * 1.0025
            
            # 2. Bullish Confirmation
            is_bullish = latest['close'] > latest['open']
            
            # 3. High Volume
            vol_ma = df['volume'].rolling(20).mean().iloc[-1]
            high_vol = latest['volume'] > vol_ma
            
            setup_detected = pullback_test and is_bullish and high_vol
            
            return {
                "is_pullback_setup": setup_detected,
                "vwap_val": vwap_now,
                "volume_ratio": round(latest['volume'] / vol_ma, 2) if vol_ma > 0 else 0
            }
        except Exception as e:
            print(f"Error in VWAP pullback detection: {e}")
            return {"is_pullback_setup": False}

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
            
            # Improved ORB: Take first 30 minutes of data regardless of interval
            start_time = today_df.index[0]
            orb_df = today_df[today_df.index < start_time + pd.Timedelta(minutes=30)]
            
            if orb_df.empty: return {} 
            
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
            current_price = today_df.iloc[-1]['close']
            
            gap_pct = ((today_open - prev_close) / prev_close) * 100
            
            # Fading: Current price is lower than the opening price of the gap
            is_fading = current_price < today_open
            
            # Volume at open relative to average
            # Use the volume of the FIRST candle of today
            opening_vol = today_df.iloc[0]['volume']
            vol_ma = df['volume'].rolling(20).mean().iloc[len(prev_df)] # MA at the time of open
            vol_ratio = opening_vol / vol_ma if vol_ma > 0 else 1.0
            
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
        except:
            return {"type": "None", "pct": 0, "is_fading": False, "vol_ratio": 0}

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
    def check_exhaustion(df: pd.DataFrame, current_price: float) -> dict:
        """
        Detects if a stock is overextended (Dangerous to buy).
        Rules: 
        1. Price > 3.5% from Day Open
        2. Price > 2.5 ATRs from 20 EMA
        """
        try:
            current_date = df.index[-1].date()
            today_df = df[df.index.date == current_date]
            if today_df.empty: return {"is_exhausted": False}

            day_open = today_df['open'].iloc[0]
            pct_from_open = ((current_price - day_open) / day_open) * 100

            ema_20 = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
            atr = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range().iloc[-1]
            
            dist_from_ema = current_price - ema_20
            atr_multiple = dist_from_ema / atr if atr > 0 else 0

            is_exhausted = pct_from_open > 3.5 or atr_multiple > 2.5
            
            reasons = []
            if pct_from_open > 3.5: reasons.append(f"Way up (+{pct_from_open:.1f}%) from open")
            if atr_multiple > 2.5: reasons.append(f"Deeply stretched from 20 EMA ({atr_multiple:.1f} ATRs)")

            return {
                "is_exhausted": is_exhausted,
                "pct_from_open": round(pct_from_open, 2),
                "atr_dist": round(atr_multiple, 2),
                "reasons": reasons
            }
        except:
            return {"is_exhausted": False}

    @staticmethod
    def identify_pullback(df: pd.DataFrame, current_price: float) -> dict:
        """
        Identifies if a stock is in a healthy pullback to support while in a BULL trend.
        Ideal for 10:30 AM entries.
        """
        try:
            ema_9 = EMAIndicator(close=df['close'], window=9).ema_indicator().iloc[-1]
            vwap = IntradayTechnicalAnalysis.calculate_vwap(df)
            
            # Check if price is within 0.5% of either support
            near_ema = abs(current_price - ema_9) / current_price < 0.005
            near_vwap = abs(current_price - vwap) / current_price < 0.005
            
            # Must be above 20 EMA to be a "Bullish" pullback
            ema_20 = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
            is_bullish = current_price > ema_20
            
            return {
                "is_pullback": (near_ema or near_vwap) and is_bullish,
                "type": "9EMA" if near_ema else "VWAP" if near_vwap else "None",
                "support_val": ema_9 if near_ema else vwap if near_vwap else 0
            }
        except:
            return {"is_pullback": False}

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
    def detect_squeeze(df: pd.DataFrame) -> dict:
        """
        Detects Bollinger Band Squeeze (Volatility Contraction).
        Squeeze = BB Width is at a low relative to history.
        """
        try:
            bb = BollingerBands(close=df['close'], window=20, window_dev=2)
            h_band = bb.bollinger_hband()
            l_band = bb.bollinger_lband()
            bb_width = (h_band - l_band) / bb.bollinger_mavg()
            
            # Squeeze: Current width < 20-period SMA of width
            width_ma = bb_width.rolling(20).mean()
            is_squeeze = bb_width.iloc[-1] < width_ma.iloc[-1] * 0.95
            
            # Breakout: Current Close > Upper Band
            is_breakout = df['close'].iloc[-1] > h_band.iloc[-1]
            
            return {
                "is_squeeze": is_squeeze,
                "is_breakout": is_breakout,
                "width": round(bb_width.iloc[-1], 4),
                "width_percentile": round((bb_width.iloc[-1] / width_ma.iloc[-1]) * 100, 1),
                "upper": round(h_band.iloc[-1], 2),
                "lower": round(l_band.iloc[-1], 2)
            }
        except:
            return {"is_squeeze": False, "is_breakout": False, "width": 0}

    @staticmethod
    def detect_rsi_divergence(df: pd.DataFrame) -> dict:
        """
        Simple RSI Divergence Detection.
        Checks if the last 5 candles show price making higher highs while RSI makes lower highs (Bearish),
        or price making lower lows while RSI makes higher lows (Bullish).
        """
        try:
            rsi = RSIIndicator(close=df['close'], window=14).rsi()
            if len(df) < 10: return {"type": "None"}
            
            # Last two local peaks/troughs comparison
            # Simplified: Compare last candle and candle 5 bars ago
            p1, p2 = df['close'].iloc[-1], df['close'].iloc[-5]
            r1, r2 = rsi.iloc[-1], rsi.iloc[-5]
            
            # Bearish Divergence: Price higher, RSI lower
            if p1 > p2 and r1 < r2 and r1 > 60:
                return {"type": "Bearish", "severity": "High" if r1 < r2 - 5 else "Moderate"}
            
            # Bullish Divergence: Price lower, RSI higher
            if p1 < p2 and r1 > r2 and r1 < 40:
                return {"type": "Bullish", "severity": "High" if r1 > r2 + 5 else "Moderate"}
                
            return {"type": "None"}
        except:
            return {"type": "None"}

    @staticmethod
    def detect_wash_and_rinse(df: pd.DataFrame) -> dict:
        """
        Detects 'Wash & Rinse' (Stop Hunt) Pattern.
        Price dips below a major level (Support, VWAP, or Prev Low) and reclaims it 
        on high volume within a short window.
        """
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
        except:
            return {"is_trap": False}

    @staticmethod
    def check_ema_fan(df: pd.DataFrame) -> dict:
        """
        Checks for EMA Fan (9, 20, 50, 200) alignment.
        Strongest trend indicator.
        """
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
        except:
            return {"status": "No Fan", "is_aligned": False, "score_bonus": 0}

    @staticmethod
    def calculate_adx(df: pd.DataFrame) -> dict:
        """
        Calculates ADX to determine trend strength.
        ADX > 25: Trending, ADX < 20: Choppy/Sideways.
        """
        try:
            if len(df) < 20: return {"adx": 0, "status": "Unknown", "bias": "Neutral", "score": 50, "is_rising": False, "adx_slope": 0.0}
            
            adx_ind = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
            adx_series = adx_ind.adx()
            adx = adx_series.iloc[-1]
            adx_prev = adx_series.iloc[-2] if len(adx_series) > 1 else adx
            plus_di = adx_ind.adx_pos().iloc[-1]
            minus_di = adx_ind.adx_neg().iloc[-1]
            
            # Trend Direction
            adx_slope = adx - adx_prev
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
        except:
            return {"adx": 0, "status": "Unknown", "bias": "Neutral", "score": 50, "is_rising": False, "adx_slope": 0.0}

    @staticmethod
    def detect_volume_cluster(df: pd.DataFrame) -> dict:
        """
        Detects Institutional Volume Clusters within the last 30 minutes.
        A cluster is defined as 3 consecutive candles with volume > 20-period average 
        AND price rising (Close > Open).
        """
        try:
            if len(df) < 10: return {"is_cluster": False}
            
            # Use last 6 candles for 30 min window (if 5m interval) or last 3 (if 10m)
            # Standardizing to check the trailing segment of the dataframe
            # Since df_15m is used in the engine, 30m = 2 candles. 
            # However, the requirement is "3 consecutive candles". 
            # We will use the last 6 candles from the dataframe (assuming 5m or 15m context)
            
            vol_ma = df['volume'].rolling(20).mean()
            
            # We check a rolling window of 3 for the condition
            # 1. Volume > MA
            # 2. Close > Open (Rising)
            cond_vol = df['volume'] > vol_ma
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
        except:
            return {"is_cluster": False}

    @staticmethod
    def detect_micro_trend(df: pd.DataFrame) -> dict:
        """
        Analyzes the last 10 candles for specific trend patterns:
        - HH + HL (Higher High + Higher Low): Score +10
        - Lower High: Penalty -10
        """
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
        except:
            return {"pattern": "None", "hh_hl": False, "lh": False}

    @staticmethod
    def detect_stop_hunt_sweep(df: pd.DataFrame) -> dict:
        """
        Pioneer V3.3 Specialized "Stop Hunt / Liquidity Sweep" Detector.
        Detects false breakouts where price traps traders above key levels.
        """
        try:
            if len(df) < 30: return {"liquidity_sweep": False}

            latest = df.iloc[-1]
            prev_1 = df.iloc[-2]
            prev_2 = df.iloc[-3] if len(df) > 2 else prev_1
            
            # 1. BREAKOUT LEVEL IDENTIFICATION
            # A. Intraday Swing High (Last 1 hour / 4 candles of 15m)
            swing_high = df['high'].iloc[-5:-1].max()
            
            # B. Opening Range High
            orb_high = 0
            if isinstance(df.index, pd.DatetimeIndex):
                today_df = df[df.index.date == df.index[-1].date()]
                if not today_df.empty:
                    orb_high = today_df['high'].iloc[0:2].max() # 15-30m range
            
            # C. VWAP Deviation resistance (Approximation)
            tp = (df['high'] + df['low'] + df['close']) / 3
            vwap = (tp * df['volume']).cumsum() / df['volume'].cumsum()
            vwap_now = vwap.iloc[-1]
            std_dev = df['close'].rolling(20).std().iloc[-1]
            vwap_res = vwap_now + (2 * std_dev)
            
            # D. Previous Day High
            pdh = 0
            if isinstance(df.index, pd.DatetimeIndex):
                dates = pd.Series(df.index.date).unique()
                if len(dates) > 1:
                    prev_day = dates[-2]
                    pdh = df[df.index.date == prev_day]['high'].max()
            
            # Identify the MOST RELEVANT breakout level (The major resistance we are testing)
            # Upgrade 1 V4.2: Priority Level Selection (Major > Minor)
            # Priority: Prev_Day_High > OR_High > Swing_High
            
            current_price = latest['close']
            breakout_level = 0
            breakout_level_source = "None"
            
            # 1. Higher Priority: Previous Day High (Within 3% range)
            if pdh > 0 and abs(pdh - current_price) / current_price < 0.03:
                breakout_level = pdh
                breakout_level_source = "Prev_Day_High"
            
            # 2. Medium Priority: Opening Range High (If PDH not valid)
            elif orb_high > 0 and abs(orb_high - current_price) / current_price < 0.03:
                breakout_level = orb_high
                breakout_level_source = "OR_High"
                
            # 3. Standard Priority: Swing High (If others not valid)
            elif swing_high > 0 and abs(swing_high - current_price) / current_price < 0.03:
                breakout_level = swing_high
                breakout_level_source = "Swing_High"
                
            # 4. Fallback: VWAP Res
            elif vwap_res > 0 and abs(vwap_res - current_price) / current_price < 0.03:
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
            if latest['close'] > breakout_level:
                breakout_strength = (latest['close'] - breakout_level) / breakout_level
                if breakout_strength < 0.003:
                    is_weak_breakout = True
            
            for i in range(-3, 0):
                if df.iloc[i]['high'] > breakout_level and df.iloc[i]['close'] > breakout_level:
                    had_breakout = True
                    breakout_index = i
                    # Capture strength from the actual breakout candle if needed
                    breakout_strength = max(breakout_strength, (df.iloc[i]['close'] - breakout_level) / breakout_level)
                    break

            # 3. LIQUIDITY SWEEP DETECTION
            liquidity_sweep = False
            stop_hunt_detected = False
            
            # Condition A: Wick High > Level AND Close < Level (Immediate Rejection)
            cond_a = latest['high'] > breakout_level and latest['close'] < breakout_level
            
            # Condition B: Closes back below within 2 candles (FAILED_BREAKOUT)
            cond_b = False
            fake_breakout_flag = False
            if had_breakout:
                # If we had a breakout in the last 2 candles but current price is below
                # breakout_index: -1 (last), -2 (prev), -3 (2nd prev)
                # If breakout was at -3 or -2 and now we are back below (latest is -1)
                if breakout_index < -1 and latest['close'] < breakout_level:
                    cond_b = True
                    fake_breakout_flag = True
            
            # Condition C: Volume spike but fail to hold
            vol_ma = df['volume'].rolling(20).mean().iloc[-1]
            rvol = latest['volume'] / vol_ma if vol_ma > 0 else 1.0
            cond_c = rvol > 1.8 and latest['high'] > breakout_level and latest['close'] < breakout_level
            
            if cond_a or cond_b or cond_c:
                liquidity_sweep = True
            
            # 4. STOP HUNT CONFIRMATION
            if liquidity_sweep and rvol > 1.8 and latest['close'] < breakout_level:
                stop_hunt_detected = True

            # 5. STATEFUL RE-ENTRY CHECK (Module 3 V4)
            # Count consecutive candles closing above the level at the end of the DF
            candle_hold_count = 0
            for i in range(len(df)-1, -1, -1):
                if df['close'].iloc[i] > breakout_level:
                    candle_hold_count += 1
                else:
                    break
            
            # Volume check: average volume over the hold duration (capped at 3 for rule validation)
            check_count = max(1, min(candle_hold_count, 3))
            reclaim_vol_avg = df['volume'].iloc[-check_count:].mean() if candle_hold_count > 0 else 0
            
            price_reclaim = False
            if candle_hold_count >= 2 and reclaim_vol_avg >= vol_ma:
                price_reclaim = True

            return {
                "liquidity_sweep": liquidity_sweep,
                "stop_hunt_detected": stop_hunt_detected,
                "fake_breakout_flag": fake_breakout_flag,
                "breakout_strength": round(breakout_strength, 4),
                "is_weak_breakout": is_weak_breakout,
                "is_breakout": latest['close'] > breakout_level,
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
        """
        V6.2: Trend Direction Guard using EMA 20/50 alignment.
        Fast (EMA20) must be above Slow (EMA50) for Bullish trend.
        """
        try:
            if len(df) < 50: return {"trend_direction_state": "NEUTRAL_TREND", "ema_alignment": False}
            
            ema_20_series = EMAIndicator(close=df['close'], window=20).ema_indicator()
            ema_50_series = EMAIndicator(close=df['close'], window=50).ema_indicator()
            
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
        """
        V6.3: Market Structure Validation using last 5 candles.
        Detects BULLISH/BEARISH/NEUTRAL structures based on structural HH/HL or LH/LL.
        """
        try:
            if len(df) < 6: return {"market_structure_state": "NEUTRAL_STRUCTURE"}
            
            # Lookback window: last 5 candles excluding current
            # prev_window = df.iloc[-6:-1]
            prev_high = df['high'].iloc[-6:-1].max()
            prev_low = df['low'].iloc[-6:-1].min()
            
            latest_high = df['high'].iloc[-1]
            latest_low = df['low'].iloc[-1]
            
            # Structure rules
            if latest_high > prev_high and latest_low > prev_low:
                state = "BULLISH_STRUCTURE"
            elif latest_high < prev_high or latest_low < prev_low:
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
        """
        V6.3 Clarification: Detects stop-hunt spikes with range expansion confirmation.
        A trap is detected ONLY if ALL 4 conditions are met:
        1. Volume Spike > 1.8x
        2. Upper Wick > 50% of candle
        3. Close in bottom 30%
        4. Range Expansion Ratio >= 1.7
        """
        try:
            if len(df) < 20: return {"trap_move_detected": False}
            
            latest = df.iloc[-1]
            
            # 1. Volume spike ratio > 1.8x volume_ma(10)
            vol_ma_series = df['volume'].rolling(10).mean()
            vol_ma = vol_ma_series.iloc[-2] if not np.isnan(vol_ma_series.iloc[-2]) else vol_ma_series.iloc[-1]
            volume_spike_ratio = latest['volume'] / vol_ma if not np.isnan(vol_ma) and vol_ma > 0 else 1.0
            cond_vol = volume_spike_ratio > 1.8
            
            # 2. Upper wick > 50% of candle
            candle_range = latest['high'] - latest['low']
            upper_wick = latest['high'] - max(latest['close'], latest['open'])
            upper_wick_ratio = upper_wick / candle_range if candle_range > 0 else 0
            cond_wick = upper_wick_ratio > 0.50
            
            # 3. Close position formula (low to high range ratio)
            # close_position = (close - low) / (high - low)
            close_position = (latest['close'] - latest['low']) / candle_range if candle_range > 0 else 0.5
            cond_close = close_position <= 0.30
            
            # 4. Range Expansion Confirmation (10-candle average)
            ranges = (df['high'] - df['low']).rolling(10).mean()
            avg_range = ranges.iloc[-2] if not np.isnan(ranges.iloc[-2]) else ranges.iloc[-1]
            range_expansion_ratio = candle_range / avg_range if not np.isnan(avg_range) and avg_range > 0 else 1.0
            cond_range = range_expansion_ratio >= 1.7
            
            trap_move_detected = cond_vol and cond_wick and cond_close and cond_range
            
            return {
                "trap_move_detected": trap_move_detected,
                "trap_range_expansion": cond_range, # FIX 4 (Patch 1): Metadata alignment
                "range_expansion_ratio": round(range_expansion_ratio, 2), # FIX 2 (Patch 2)
                "details": {
                    "vol_spike": cond_vol,
                    "upper_wick_ratio": round(upper_wick_ratio, 2),
                    "close_position": round(close_position, 2),
                    "range_expansion_ratio": round(range_expansion_ratio, 2)
                }
            }
        except Exception as e:
            # print(f"Error in Liquidity Trap Detection: {e}") # Debugging
            return {"trap_move_detected": False, "trap_range_expansion": False}

    @staticmethod
    def detect_smart_money_accumulation(df: pd.DataFrame) -> dict:
        """
        Pioneer V3.4 Smart Money Accumulation Detector.
        Detects quiet institutional buying activity before a major breakout.
        """
        try:
            if len(df) < 30: return {"accumulation_detected": False}

            latest = df.iloc[-1]
            # --- 1. CONSOLIDATION DETECTION ---
            # Using last 20 candles
            last_20 = df.tail(20)
            highest_high = last_20['high'].max()
            lowest_low = last_20['low'].min()
            current_price = latest['close']
            
            range_pct = (highest_high - lowest_low) / (current_price if current_price > 0 else 1) * 100
            
            # Price above or near VWAP check
            vwap_series = IntradayTechnicalAnalysis.calculate_vwap_series(df)
            vwap_now = vwap_series.iloc[-1]
            
            # price remains above or near VWAP (< 0.5% offset if below)
            price_near_vwap = current_price >= vwap_now * 0.995 
            
            consolidation_zone = (range_pct < 2.5) and price_near_vwap

            # --- 2. ACCUMULATION VOLUME PATTERN ---
            # Avg vol last 10 vs Avg vol previous 10 (10-20 ago)
            avg_vol_last_10 = last_20['volume'].tail(10).mean()
            avg_vol_prev_10 = last_20['volume'].iloc[0:10].mean()
            
            volume_acc_ratio = avg_vol_last_10 / (avg_vol_prev_10 if avg_vol_prev_10 > 0 else 1)
            volume_accumulation = volume_acc_ratio > 1.25

            # --- 3. SHALLOW PULLBACK DETECTION ---
            # Pullbacks remain within 1.5%-2% range
            # Lows are gradually rising (Low[-1] > Low[-10])
            pullbacks_shallow = True
            for i in range(-5, 0):
                # pullback from local 20-candle high
                pb = (highest_high - df.iloc[i]['low']) / (highest_high if highest_high > 0 else 1) * 100
                if pb > 2.0:
                    pullbacks_shallow = False
                    break
            
            higher_lows = latest['low'] > df['low'].iloc[-10]
            higher_lows_pattern = pullbacks_shallow and higher_lows

            # --- 4. VWAP SUPPORT CHECK ---
            # Price touches VWAP multiple times and rebounds above
            touches = 0
            for i in range(-20, 0):
                # Touch = low near vwap, Rebound = close above vwap
                if df.iloc[i]['low'] <= vwap_series.iloc[i] * 1.002 and df.iloc[i]['close'] > vwap_series.iloc[i]:
                    touches += 1
            
            vwap_accumulation_support = touches >= 2

            # --- 5. ACCUMULATION CONFIRMATION ---
            # V6.1: Accumulation must last minimum 4 candles
            # We verify that consolidation was valid for at least 4 bars
            def is_consolidating(idx_offset):
                slice_df = df.iloc[idx_offset-20:idx_offset] if idx_offset >= 20 else df.iloc[:idx_offset]
                if slice_df.empty: return False
                s_high = slice_df['high'].max()
                s_low = slice_df['low'].min()
                s_range = (s_high - s_low) / (slice_df['close'].iloc[-1] if not slice_df['close'].empty else 1) * 100
                return s_range < 2.5

            duration_validation = all([is_consolidating(i) for i in range(len(df), len(df)-4, -1)])
            
            accumulation_detected = (
                consolidation_zone and 
                volume_accumulation and 
                higher_lows_pattern and 
                vwap_accumulation_support and
                duration_validation
            )

            # --- 7. BREAKOUT & INVALIDATION DATA ---
            is_breakout = current_price > highest_high
            is_breakdown = current_price < lowest_low

            return {
                "accumulation_detected": accumulation_detected,
                "consolidation_range_percent": round(range_pct, 2),
                "volume_accumulation_ratio": round(volume_acc_ratio, 2),
                "avg_vol_consolidation": float(last_20['volume'].mean()),
                "consolidation_high": float(highest_high),
                "consolidation_low": float(lowest_low),
                "is_breakout": is_breakout,
                "is_breakdown": is_breakdown,
                "pattern_label": "Smart Money Accumulation" if accumulation_detected else "None"
            }
        except Exception as e:
            print(f"Error in Accumulation Detection: {e}")
            return {"accumulation_detected": False}

    @staticmethod
    def check_ema_stack(df: pd.DataFrame) -> dict:
        """
        Checks for EMA Alignment setup:
        - Price > EMA9
        - EMA9 > EMA20
        - EMA20 slope upward
        """
        try:
            if len(df) < 20: return {"is_aligned": False, "ema20_slope_up": False}

            ema_9 = EMAIndicator(close=df['close'], window=9).ema_indicator()
            ema_20 = EMAIndicator(close=df['close'], window=20).ema_indicator()

            close_now = df['close'].iloc[-1]
            ema_9_now = ema_9.iloc[-1]
            ema_20_now = ema_20.iloc[-1]
            ema_20_prev = ema_20.iloc[-2]

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
    def calculate_poc(df: pd.DataFrame) -> float:
        """
        Calculates the Volume Profile Point of Control (POC) for the day.
        POC is the price level with the highest traded volume.
        """
        try:
            if isinstance(df.index, pd.DatetimeIndex):
                current_date = df.index[-1].date()
                today_df = df[df.index.date == current_date]
            else:
                today_df = df.tail(75) # Fallback for non-timed data
            
            if today_df.empty: return df['close'].iloc[-1]
            
            # Use 50 bins for the price range of the day
            min_p = today_df['low'].min()
            max_p = today_df['high'].max()
            if min_p == max_p: return min_p
            
            bins = np.linspace(min_p, max_p, 51)
            # Assign volume to bins based on candle high/low/close average
            prices = (today_df['high'] + today_df['low'] + today_df['close']) / 3
            volume_profile, _ = np.histogram(prices, bins=bins, weights=today_df['volume'])
            
            # Find the bin with max volume
            max_bin_idx = np.argmax(volume_profile)
            poc = (bins[max_bin_idx] + bins[max_bin_idx+1]) / 2
            return float(poc)
        except:
            return float(df['close'].iloc[-1])

    @staticmethod
    def detect_poc_bounce(df: pd.DataFrame) -> dict:
        """
        Detects if price pulls back to POC and shows a bullish reversal candle with volume.
        Logic:
        1. Low <= POC * 1.002 (Near touch)
        2. Close > Open (Bullish)
        3. Volume > 20-period Average Volume
        """
        try:
            if len(df) < 20: return {"is_bounce": False}
            
            poc = IntradayTechnicalAnalysis.calculate_poc(df)
            latest = df.iloc[-1]
            
            # 1. Test of POC
            near_poc = latest['low'] <= poc * 1.002 and latest['high'] >= poc * 0.998
            
            # 2. Bullish Confirmation
            is_bullish = latest['close'] > latest['open']
            
            # 3. High Volume
            vol_ma = df['volume'].rolling(20).mean().iloc[-1]
            high_vol = latest['volume'] > vol_ma
            
            is_bounce = near_poc and is_bullish and high_vol
            
            return {
                "is_bounce": is_bounce,
                "poc_val": round(poc, 2),
                "volume_ratio": round(latest['volume'] / vol_ma, 2) if vol_ma > 0 else 0
            }
        except Exception as e:
            print(f"Error in POC bounce detection: {e}")
            return {"is_bounce": False}

    @staticmethod
    def calculate_cvd_proxy(df: pd.DataFrame) -> dict:
        """
        Calculates a Cumulative Volume Delta (CVD) Proxy.
        Approximates Buying/Selling pressure by assigning volume to buyers if close > open,
        and to sellers if close < open. Focuses on the intraday trend.
        """
        try:
            if not isinstance(df.index, pd.DatetimeIndex): return {"cvd": 0, "status": "Neutral", "score": 50}
            
            # Analyze only today's volume flow
            current_date = df.index[-1].date()
            today_df = df[df.index.date == current_date]
            
            if today_df.empty: return {"cvd": 0, "cvd_ratio": 0.0, "status": "Neutral", "score": 50}
            
            buy_vol = today_df[today_df['close'] > today_df['open']]['volume'].sum()
            sell_vol = today_df[today_df['close'] < today_df['open']]['volume'].sum()
            
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
        except:
             return {"cvd": 0, "cvd_ratio": 0.0, "status": "Neutral", "score": 50}

    @staticmethod
    def analyze_stock(df: pd.DataFrame) -> dict:
        """Institutional-grade Intraday Analysis using specific weighted indicators."""
        if df.empty or len(df) < 20: return {}
        
        latest = df.iloc[-1]
        
        # 1. VWAP (30% weight in engine) - Daily anchor is standard
        vwap_ctx = IntradayTechnicalAnalysis.analyze_vwap_advanced(df)
        
        # Ensure close and vwap are scalars (handle potential duplicate columns/Series)
        close = latest['close']
        vwap = vwap_ctx["vwap_val"]
        
        close_val = float(close.iloc[0]) if hasattr(close, "iloc") else float(close)
        vwap_val = float(vwap.iloc[0]) if hasattr(vwap, "iloc") else float(vwap)
        
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
        
        current_vol = latest['volume']
        rvol_time_reference = current_time
        
        if avg_vol_at_time > 0:
            rvol = current_vol / avg_vol_at_time
        else:
            # Fallback: RVOL = Current Volume / (ADV20 / 25 expected candles per session)
            # Standard time-normalized intraday benchmarking divisor fixed at 25
            avg_candle_vol = adv20 / 25 if adv20 > 0 else df['volume'].rolling(20).mean().iloc[-1]
            rvol = current_vol / avg_candle_vol if avg_candle_vol > 0 else 1.0
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
        atr_val = atr_series.iloc[-1]
        if pd.isna(atr_val) or atr_val == 0: atr_val = close * 0.015
        
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
        valid_res = [v for k, v in pivots.items() if v > close]
        target = min(valid_res) if (valid_res and min(valid_res) > close * 1.002) else close + tp_dist
        
        valid_sup = [v for k, v in pivots.items() if v < close]
        best_sup = max(valid_sup) if (valid_sup and max(valid_sup) < close * 0.998) else close - sl_dist
        
        # Trailing stops use the ATR distance solely, ignoring pivots if it's parabolic
        if is_trailing:
            stop_loss = close - sl_dist
        else:
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
        
        target_reason = "Technical Resistance Area" if valid_res and not is_trailing else "ATR Momentum Extension"
        
        # Special Bonus Events (Still mapped for the Engine to view)
        orb = IntradayTechnicalAnalysis.detect_orb(df)
        gap = IntradayTechnicalAnalysis.analyze_gap(df)
        exhaustion = IntradayTechnicalAnalysis.check_exhaustion(df, close)
        pullback = IntradayTechnicalAnalysis.identify_pullback(df, close)
        squeeze = IntradayTechnicalAnalysis.detect_squeeze(df)
        divergence = IntradayTechnicalAnalysis.detect_rsi_divergence(df)
        trap = IntradayTechnicalAnalysis.detect_liquidity_trap(df)
        sweep = IntradayTechnicalAnalysis.detect_stop_hunt_sweep(df)
        poc_bounce = IntradayTechnicalAnalysis.detect_poc_bounce(df)
        
        # Anti-Chasing: Distance from ideal entry (VWAP or Pivot)
        best_entry = vwap if vwap_score == 100 else pivots.get("P", close)
        chase_dist = (close - best_entry) / atr_val if atr_val > 0 else 0
        
        # STRICT CHASE: If ADX isn't soaring, chasing > 1.0 ATR is highly dangerous.
        chase_threshold = 1.6 if is_trailing else 1.0
        is_chasing = chase_dist > chase_threshold 
        
        ladder = IntradayTechnicalAnalysis.calculate_ladder(df, close)
        
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
            "trap_range_expansion": trap.get("trap_range_expansion", False),
            "chase": {
                "is_chasing": is_chasing,
                "dist_atr": round(chase_dist, 2)
            }
        }

ta_intraday = IntradayTechnicalAnalysis()
