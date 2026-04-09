import asyncio
import pandas as pd
import numpy as np
import time
from app.services.market_data import market_service
from app.services.index_context import index_ctx
from app.services.liquidity_service import liquidity_service
import app.services.ta_intraday as ta_intraday
from app.services.utils import STATIC_FULL_LIST, sanitize_data
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
import pytz
from datetime import datetime, timedelta
from app.core.config import settings

def safe_scalar(x):
    if x is None: return 0.0
    val = float(x.iloc[0]) if hasattr(x, 'iloc') else float(x)
    return float(np.nan_to_num(val, nan=0.0))

class IntradayEngine:
    """
    [V11 RESTORED] Ultra-Sync Institutional Engine.
    Restores the full 12-point Audit Grid with V10 Pulse Concurrency (2200+ Symbols).
    """

    def __init__(self):
        # 🛰️ Pulse-Fire Concurrency
        self.semaphore = asyncio.Semaphore(50) 
        self.job_states = {}
        
        # 🚩 [V12.8] INSTITUTIONAL SCORING FLAGS
        self.SCORING_FLAGS = {
            "enable_smooth_alpha": True,
            "enable_dynamic_ema": True,
            "enable_vwap_precision": True,
            "enable_adx_di_validation": True,
            "enable_phantom_pre_filter": True,
            "enable_sideways_regime": True,
            "enable_time_decay": True,
            "enable_mtf_bonus": True,
            "enable_dna_gate": True,
            "enable_pa_scaling": True,
            "enable_momentum_leader": True,
            "enable_extended_structure": True,
            "enable_dynamic_dna": True,
            "debug_dna_mode": True,
            "enable_dynamic_alpha": True,
            "debug_alpha_mode": True
        }

    async def _get_index_context(self):
        """[V11 RESTORED] Complex Market Regime Audit."""
        try:
            nifty_df = await market_service.get_ohlc("^NSEI", period="2d", interval="5m")
            if nifty_df is None or nifty_df.empty: 
                return {"score": 50, "market_regime": "Mixed", "ad_ratio": 1.0, "day_change_pct": 0.0}
            
            close = nifty_df['close'].iloc[-1]
            vwap = ta_intraday.IntradayTechnicalAnalysis.calculate_vwap(nifty_df)
            ad_ratio = await market_service.get_advance_decline_ratio()
            sector_perfs = await market_service.get_sector_performances()
            
            # [V12.7] Sideways Detection
            adx_ctx = ta_intraday.IntradayTechnicalAnalysis.calculate_adx(nifty_df)
            is_sideways = adx_ctx.get("adx", 0) < 20
            
            regime = "Strong Bullish" if close > vwap and ad_ratio > 1.2 else "Mixed"
            if close < vwap and ad_ratio < 0.8: regime = "Strong Bearish"

            return {
                "market_trend": "Bullish" if close > vwap else "Bearish",
                "market_regime": regime,
                "is_sideways": is_sideways,
                "ad_ratio": ad_ratio, "sector_perfs": sector_perfs,
                "day_change_pct": round(((close - nifty_df['open'].iloc[0])/nifty_df['open'].iloc[0])*100, 2)
            }
        except: return {"score": 50, "market_regime": "Mixed"}

    async def analyze_stock(self, sym: str, job_id: str = None, global_index_ctx: dict = None, pulse_data: dict = None):
        """
        [V11 RESTORED] Full 12-Point Alpha Audit.
        Total restoration of Layer 1, 2, and 3 logic.
        """
        reasons = [] 
        try:
            # 0. Context Extraction [V12.1 FIX]
            # 1. INITIAL CONTEXT EXTRACTION (V12.1 RESTORED) 🎯
            market_regime = global_index_ctx.get("market_regime", "NEUTRAL") if global_index_ctx else "NEUTRAL"
            
            df_15m = None
            real_price = 0.0

            df_1h = None
            if pulse_data and sym in pulse_data:
                # PULSE DATA could be a pd.DataFrame (from batch) or a dict (from on-demand)
                item = pulse_data[sym]
                if isinstance(item, pd.DataFrame):
                    df_15m = item
                    real_price = float(df_15m['close'].iloc[-1]) if not df_15m.empty else 0.0
                elif isinstance(item, dict):
                    df_15m = item.get("15m")
                    df_1h = item.get("1h")
                    real_price = item.get("price", 0.0)
            else:
                df_15m = await market_service.get_ohlc(sym, period="7d", interval="15m")
                if self.SCORING_FLAGS.get("enable_mtf_bonus"):
                    df_1h = await market_service.get_ohlc(sym, period="15d", interval="60m")
                pinfo = await market_service.get_live_price(sym)
                real_price = pinfo.get("price", 0.0)

            # [V12.3 SURVIVAL THRESHOLD] 🆘
            # Reduced from 40 to 20 to allow signals in rate-limited environments
            if df_15m is None or df_15m.empty or len(df_15m) < 20:
                return {"symbol": sym, "skip_reason": "Data Depleted"}
            
            # Ensure price extraction is robust [V12.7 GUARD]
            if real_price <= 0:
                real_price = float(df_15m['close'].iloc[-1])
            
            if real_price <= 0:
                return {"symbol": sym, "skip_reason": "Price Invalid (0.0)"}

            # 2. FULL INSTITUTIONAL GRID ACTIVATION [V12.1 TRUTH] 🕵️‍♂️📊⚖️
            ta_15m = ta_intraday.analyze_stock(df_15m)
            pb_v6 = ta_intraday.detect_pullback_entry_v45(df_15m, real_price)
            micro = ta_intraday.detect_micro_trend(df_15m)
            
            reasons = []
            mtf_impact = 0.0
            timing_impact = 0.0
            # --- LAYER 1: DNA (MAX 40.0 pts) ---
            # Data Extraction for Dynamic Logic
            vwap_val = ta_15m.get("vwap_val", 0)
            vol_ratio = ta_15m.get("rvol_val", 1.0)

            # NEW LOGIC START: DNA Mode Detection (Auto Switching)
            dna_mode = "STRICT"
            l1_scale = 1.0
            if self.SCORING_FLAGS.get("enable_dynamic_dna"):
                distance_from_vwap = abs(real_price - vwap_val) / vwap_val if vwap_val > 0 else 0
                
                # Fetch 15m EMA20 Slope
                ema20_series = ta_intraday.EMAIndicator(close=df_15m['close'], window=20).ema_indicator()
                ema20_15m = ema20_series.iloc[-1]
                ema20_15m_prev = ema20_series.iloc[-2]
                ema20_slope_15m = ema20_15m - ema20_15m_prev
                
                is_trending_dna = (
                    real_price > ema20_15m and 
                    ema20_slope_15m > 0 and 
                    vol_ratio > 2.0
                )
                
                if is_trending_dna and distance_from_vwap > 0.01:
                    dna_mode = "RELAXED"
                    l1_scale = 0.7
                
                # Safety Fallback
                if dna_mode == "RELAXED" and vol_ratio < 1.5:
                    dna_mode = "STRICT"
                    l1_scale = 1.0
            # NEW LOGIC END

            # VWAP Alignment (12.0)
            vw_score = ta_15m.get("vwap_score", 0)
            vw_impact = round((max(vw_score - 40, 0) * 0.233), 1) # [V12.7 CONSISTENCY] Max 14.0
            
            # NEW LOGIC START: VWAP Relaxation
            if self.SCORING_FLAGS.get("enable_dynamic_dna") and dna_mode == "RELAXED":
                vw_impact *= 0.6
            # NEW LOGIC END
            
            # Apply L1 Scaling
            vw_impact *= l1_scale
            
            reasons.append({
                "text": "VWAP Alignment" if vw_impact > 0 else "Weak VWAP Alignment", 
                "type": "positive" if vw_impact > 0 else "negative", 
                "impact": vw_impact, 
                "layer": 1
            })
            
            # ADX Momentum (10.0)
            adx_score = ta_15m.get("adx_score", 0)
            adx_bias = ta_15m.get("bias", "Neutral")
            adx_impact = round((max(adx_score - 25, 0) * 0.16), 1) # [V12.7 CONSISTENCY] Max 12.0
            adx_impact *= l1_scale
            
            # [V12.7] ADX Direction Validation
            if self.SCORING_FLAGS["enable_adx_di_validation"]:
                # FIX START: Ensure ADX Bearish case always logs reason
                if adx_bias == "Bearish":
                    if not micro.get("hh_hl", False):
                        adx_impact *= 0.5
                    reasons.append({
                        "text": "ADX Momentum Audit (Bearish DI)",
                        "type": "negative",
                        "impact": adx_impact,
                        "layer": 1
                    })
                # FIX END
                elif adx_bias == "Bullish":
                    reasons.append({
                        "text": "ADX Momentum Audit (Bullish DI)" if adx_impact > 0 else "Weak ADX Momentum", 
                        "type": "positive" if adx_impact > 0 else "negative", 
                        "impact": adx_impact, 
                        "layer": 1
                    })
                else:
                    reasons.append({
                        "text": "ADX Momentum Audit" if adx_impact > 0 else "Weak ADX Momentum", 
                        "type": "positive" if adx_impact > 0 else "negative", 
                        "impact": adx_impact, 
                        "layer": 1
                    })
            else:
                reasons.append({
                    "text": "ADX Momentum Audit" if adx_impact > 0 else "Weak ADX Momentum", 
                    "type": "positive" if adx_impact > 0 else "negative", 
                    "impact": adx_impact, 
                    "layer": 1
                })
            
            # Price Action (10.0)
            pa_score = ta_15m.get("pa_score", 0)
            # NEW LOGIC START: PA Scaling (Remove pulse-drop behavior)
            if self.SCORING_FLAGS.get("enable_pa_scaling"):
                pa_impact = round((max(pa_score - 40, 0) * 0.30) * 0.40, 1) # [V12.7 BOOST] Max 7.2
            else:
                if pa_score > 55:
                    pa_impact = round((pa_score * 0.25) * 0.40, 1) # Max 10.0
                else:
                    pa_impact = 0
            
            pa_impact *= l1_scale
            
            if pa_impact > 0:
                reasons.append({"text": "Price Action Validity", "type": "positive", "impact": pa_impact, "layer": 1})
            else:
                reasons.append({"text": "Weak Buying Pressure", "type": "negative", "impact": 0.0, "layer": 1})
            # NEW LOGIC END
            
            # Volume DNA (8.0)
            vol_impact = round((min(vol_ratio, 4.0) * 10 * 0.20) * 0.40, 1) # Max 8.0
            vol_impact *= l1_scale
            reasons.append({"text": "Volume DNA Cluster", "type": "positive" if vol_ratio > 1.2 else "negative", "impact": vol_impact, "layer": 1})

            # --- V12.7 Smooth Weighting Redux ---
            v6_elite_score = 45.0 if self.SCORING_FLAGS["enable_smooth_alpha"] else 60.0
            v45_pb_score = 25.0 if self.SCORING_FLAGS["enable_smooth_alpha"] else 30.0
            
            # [V12.7] VWAP Precision Proximity
            vwap_threshold = 0.01 # Standard 1%
            if self.SCORING_FLAGS["enable_vwap_precision"]:
                liq = liquidity_service.get_liquidity(sym)
                liq_level = liq.get("level")
                if liq_level == "High": vwap_threshold = 0.005 # Large Cap: 0.5%
                elif liq_level: vwap_threshold = 0.012 # Mid/Small: 1.2% (RECALIBRATED)

            # FIX START: VWAP Division Safety (Ensures division by zero protection)
            vwap_hook = abs(real_price - vwap_val) / vwap_val < vwap_threshold if vwap_val > 0 else False
            # FIX END
            ignition = vol_ratio > 1.5 
            # NEW LOGIC START: Extended HH-HL Detection
            if self.SCORING_FLAGS.get("enable_extended_structure"):
                is_hh_hl_extended = False
                if len(df_15m) >= 6:
                    recent_highs = df_15m['high'].iloc[-6:].values
                    recent_lows = df_15m['low'].iloc[-6:].values
                    if all(recent_highs[i] < recent_highs[i+1] for i in range(len(recent_highs)-1)) and \
                       all(recent_lows[i] < recent_lows[i+1] for i in range(len(recent_lows)-1)):
                        is_hh_hl_extended = True
                
                # Merge with existing logic (Additive)
                is_hh_hl = micro.get("hh_hl", False) or is_hh_hl_extended
            else:
                is_hh_hl = micro.get("hh_hl", False)
            # NEW LOGIC END

            # NEW LOGIC START: Alpha Mode Detection
            alpha_mode = "NONE"
            if self.SCORING_FLAGS.get("enable_dynamic_alpha"):
                distance_from_vwap = abs(real_price - vwap_val) / vwap_val if vwap_val > 0 else 0
                
                ema20 = ta_15m.get("ema20", 0)
                ema20_prev = ta_15m.get("ema20_prev", ema20)
                ema20_slope = ema20 - ema20_prev

                is_trending = (
                    real_price > ema20 and
                    ema20_slope > 0 and
                    vol_ratio > 1.0 # RECALIBRATED (was 1.2)
                )

                is_pullback = pb_v6.get("is_entry")
                is_near_vwap = distance_from_vwap < vwap_threshold
                
                # BUG FIX: Don't overwrite is_hh_hl calculated above at line 257
                # is_hh_hl = micro.get("hh_hl", False) 

                # PRIORITY ORDER (RECALIBRATED)
                if is_near_vwap and is_trending and is_hh_hl:
                    alpha_mode = "EARLY"
                elif is_trending and distance_from_vwap > vwap_threshold and vol_ratio > 1.5: # RECALIBRATED (was 2.0)
                    alpha_mode = "MOMENTUM"
                elif is_pullback:
                    alpha_mode = "PULLBACK"
                
                # Internal Trace (Temporary)
                # print(f"DEBUG: {sym} | vwap:{is_near_vwap} | trend:{is_trending} | hhhl:{is_hh_hl} | vol:{vol_ratio} | mode:{alpha_mode}")

                # Alpha Safety Gate: Enforce DNA Floor
                # Note: layer1_score is calculated after L1 impacts are assigned
                l1_temp_score = round(vw_impact + adx_impact + pa_impact + vol_impact, 1)
                
                # DIAGNOSTIC START: Explain why L2 is Zero
                if alpha_mode == "NONE":
                    if l1_temp_score < 20:
                        reasons.append({"text": "L2: Blocked by DNA Safety Gate (L1 < 20)", "type": "neutral", "impact": 0, "layer": 2})
                    elif not is_trending and vol_ratio < 1.2:
                        reasons.append({"text": "L2: No Alpha Trigger (Volume Refusal)", "type": "neutral", "impact": 0, "layer": 2})
                    elif not is_hh_hl:
                        reasons.append({"text": "L2: No Alpha Trigger (Structure Failure)", "type": "neutral", "impact": 0, "layer": 2})
                    else:
                        reasons.append({"text": "L2: Searching for Optimal Entry Mode...", "type": "neutral", "impact": 0, "layer": 2})

                if l1_temp_score < 20:
                    alpha_mode = "NONE"
                # DIAGNOSTIC END
            # NEW LOGIC END

            # Controlled Primary Trigger
            pioneer_bonus = 0
            if self.SCORING_FLAGS.get("enable_dynamic_alpha"):
                if alpha_mode == "EARLY":
                    pioneer_bonus = 45.0
                    reasons.append({"text": "Pioneer V6 ELITE (Dynamic)", "type": "positive", "label": "V6-DYN", "impact": pioneer_bonus, "layer": 2})
                elif alpha_mode == "MOMENTUM":
                    pioneer_bonus = 20.0
                    reasons.append({"text": "Momentum Leader", "type": "positive", "label": "MOM-L", "impact": pioneer_bonus, "layer": 2})
                elif alpha_mode == "PULLBACK":
                    pioneer_bonus = 25.0
                    reasons.append({"text": "Pioneer V4.5 Pullback", "type": "positive", "label": "V4.5", "impact": pioneer_bonus, "layer": 2})
            else:
                # Fallback to existing logic (Backward Compatibility)
                # DIAGNOSTIC START: L2 Catalyst Audit
                if vwap_hook and ignition and is_hh_hl:
                    pioneer_bonus = v6_elite_score
                    reasons.append({"text": "Pioneer V6 ELITE Setup", "type": "positive", "label": "V6-ELITE", "impact": pioneer_bonus, "layer": 2})
                elif vwap_hook and is_hh_hl and vol_ratio > 1.2:
                    pioneer_bonus = 20.0
                    reasons.append({"text": "Pioneer Elite-Lite Setup", "type": "positive", "label": "ELITE-L", "impact": pioneer_bonus, "layer": 2})
                elif pb_v6.get("is_entry"):
                    pioneer_bonus = v45_pb_score
                    reasons.append({"text": "Pioneer V4.5 Pullback", "type": "positive", "label": "V4.5", "impact": pioneer_bonus, "layer": 2})
            
            # --- Secondary Boosters (Independent & Stackable) ---
            sm_weight = 5.0 if self.SCORING_FLAGS["enable_smooth_alpha"] else 3.0
            inst_weight = 5.0 if self.SCORING_FLAGS["enable_smooth_alpha"] else 2.0
            
            # Smart Money Accumulation (~5.0)
            acc_bonus = sm_weight*10 if ta_15m.get("is_accumulating") else 0
            sm_impact = round(acc_bonus * 0.1, 1)
            if sm_impact > 0:
                reasons.append({"text": "Smart Money Absorption", "type": "positive", "label": "SMART", "impact": sm_impact, "layer": 2})
            
            # Inst Vol Ignition (~5.0)
            vol_ignition_bonus = inst_weight*10 if vol_ratio > 2.5 else 0
            inst_vol_impact = round(vol_ignition_bonus * 0.1, 1)
            if inst_vol_impact > 0:
                reasons.append({"text": "Institutional Vol Spark", "type": "positive", "label": "INST", "impact": inst_vol_impact, "layer": 2})

            # NEW LOGIC START: Window Timing Bonus (Relocated to Layer 2 Catalyst)
            try:
                import datetime as _dt
                import pytz as _pytz
                _now = _dt.datetime.now(_pytz.timezone("Asia/Kolkata"))
                curr_time = _now.strftime("%H:%M")
                is_optimal_window = ("09:25" <= curr_time <= "09:35") or ("14:25" <= curr_time <= "14:45")
                if is_optimal_window:
                    reasons.append({"text": "TIMING: Optimal Entry Window", "type": "positive", "impact": 3.0, "layer": 2})
                    timing_impact = 3.0
            except Exception as e:
                # Don't let timing bonus crash the whole engine logic
                pass
            # NEW LOGIC END
            
            # NEW LOGIC START: Momentum Leader Path (LEGACY - Disabled when dynamic_alpha is ON)
            if self.SCORING_FLAGS.get("enable_momentum_leader") and not self.SCORING_FLAGS.get("enable_dynamic_alpha"):
                # Avoid double counting if V6/Lite already hit
                if pioneer_bonus == 0:
                    distance_from_vwap = abs(real_price - vwap_val) / vwap_val if vwap_val > 0 else 0
                    
                    # Calculate 15m EMA20 Slope
                    ema20_series = ta_intraday.EMAIndicator(close=df_15m['close'], window=20).ema_indicator()
                    ema20_15m = ema20_series.iloc[-1]
                    ema20_15m_prev = ema20_series.iloc[-2]
                    ema20_slope_15m = ema20_15m - ema20_15m_prev
                    
                    is_trending_momentum = (
                        real_price > ema20_15m and 
                        ema20_slope_15m > 0 and 
                        vol_ratio > 2.0
                    )
                    
                    # Ensure structure isn't bearish
                    is_not_bearish = micro.get("market_structure_state", "NEUTRAL_STRUCTURE") != "BEARISH_STRUCTURE"
                    
                    # Rule: Must be beyond standard VWAP threshold to trigger Momentum Leader path
                    if distance_from_vwap > vwap_threshold and is_trending_momentum and is_not_bearish:
                        momentum_bonus = 25.0
                        reasons.append({
                            "text": "Momentum Leader (VWAP Expansion + Volume)", 
                            "type": "positive", 
                            "impact": momentum_bonus, 
                            "layer": 2
                        })
            # NEW LOGIC END

            # FIX START: MTF Bonus Logical Placement (Ensures grouping within Alpha Edge)
            # [V12.7] Multi-Timeframe Confirmation (+5.0 Bonus)
            if self.SCORING_FLAGS["enable_mtf_bonus"] and df_1h is not None and not df_1h.empty:
                try:
                    close_1h = df_1h['close'].iloc[-1]
                    ema20_1h_series = ta_intraday.EMAIndicator(close=df_1h['close'], window=20).ema_indicator()
                    ema20_1h = ema20_1h_series.iloc[-1]
                    ema20_1h_slope = ema20_1h - ema20_1h_series.iloc[-2]
                    
                    if close_1h > ema20_1h and ema20_1h_slope > 0:
                        reasons.append({"text": "BONUS: 1H Trend Confirmation", "type": "positive", "impact": 5.0, "layer": 2})
                        mtf_impact = 5.0
                except: mtf_impact = 0
            # FIX END

            # --- LAYER 3: SAFEGUARDS (DYNAMIC PENALTIES) ---
            # 1. Trend Gravity: Price < EMA20 (-50.0)
            ema20 = ta_15m.get("ema20", 0)
            if real_price < ema20:
                # [V12.7] Dynamic EMA20 Penalty
                structure_state = micro.get("market_structure_state", "NEUTRAL_STRUCTURE")
                if self.SCORING_FLAGS["enable_dynamic_ema"] and structure_state != "BEARISH_STRUCTURE":
                    # Only apply mild penalty if structure is still holding HH/HL or Neutral
                    reasons.append({"text": "GRAVITY: Testing EMA20 Anchor", "type": "neutral", "impact": -15.0, "layer": 3})
                else:
                    # [V12.7 RECALIBRATION] Relaxed FATAL penalty to -35.0 to avoid zeroing out valid setups
                    reasons.append({"text": "FATAL: Below EMA20 Gravity", "type": "negative", "impact": -35.0, "layer": 3})
            elif self.SCORING_FLAGS["enable_dynamic_ema"] and ema20 > 0 and abs(real_price - ema20)/ema20 < 0.005:
                # Price is within 0.5% of EMA20 (Mild penalty to prevent chasing far from anchor)
                reasons.append({"text": "GRAVITY: Within EMA20 Buffer", "type": "neutral", "impact": -10.0, "layer": 3})
            
            # 2. Regime Guard: Strong Bearish (-15.0) [RECALIBRATED]
            if market_regime.upper() == "STRONG BEARISH":
                reasons.append({"text": "REGIME: Nifty Strong Bearish", "type": "negative", "impact": -15.0, "layer": 3})
            elif self.SCORING_FLAGS["enable_sideways_regime"] and global_index_ctx and global_index_ctx.get("is_sideways"):
                # NEW LOGIC START: Relaxed Sideways Penalty for Outliers
                side_impact = -5.0 if vol_ratio > 1.5 else -10.0
                reasons.append({"text": "REGIME: Market Sideways [ADX Low]", "type": "negative", "impact": side_impact, "layer": 3})
                # NEW LOGIC END
            
            # [V12.6] Overhead Rejection Filter (-15.0)
            # Detect Inverted Hammers / Sharp Rejections
            last_candle = ta_15m.get("last_candle", {})
            if last_candle:
                h, l, c, o = last_candle.get('h', 0), last_candle.get('l', 0), last_candle.get('c', 0), last_candle.get('o', 0)
                full_range = max(h - l, 0.001)
                upper_wick = h - max(o, c)
                if (upper_wick / full_range) > 0.60:
                    reasons.append({"text": "REJECTION: Sharp Overhead Supply", "type": "negative", "impact": -15.0, "layer": 3})
            
            # 3. Risk/Reward Mathematical Guard (-15.0)
            # [V12.5 PROFESSIONAL RR & HIKE GUARD] 🛡️
            target_p = ta_15m.get("resistance", real_price * 1.03)
            sl_p = ta_15m.get("support", real_price * 0.98)
            
            # Ensure Target is at least 1.5x the Risk away
            risk = max(real_price - sl_p, real_price * 0.005) # Min 0.5% risk floor
            min_reward = risk * 1.5
            if (target_p - real_price) < min_reward:
                target_p = real_price + min_reward
                
            rr_ratio = (target_p - real_price) / max(risk, 0.001)
            hike_pct = ((target_p - real_price) / max(real_price, 0.001)) * 100
            
            # NEW LOGIC START: RR Smoothing (Tiered Penalties)
            if rr_ratio < 1.2:
                reasons.append({"text": "RISK: Poor RR (<1.2)", "type": "negative", "impact": -15.0, "layer": 3})
            elif rr_ratio < 1.4:
                reasons.append({"text": "RISK: Suboptimal RR (1.2–1.4)", "type": "negative", "impact": -5.0, "layer": 3})
            # NEW LOGIC END
            
            if hike_pct < 1.0: # Ensure at least 1% 'meat on the bone'
                reasons.append({"text": f"PROFIT: Tight Hike Potential ({hike_pct:.1f}%)", "type": "negative", "impact": -10.0, "layer": 3})

            # 4. Weak Volume Guard (-10.0)
            # [V12.7] Phantom Volume Pre-Filter: Cap achievable score to 70 if RVOL < 1.2
            if self.SCORING_FLAGS["enable_phantom_pre_filter"] and vol_ratio < 1.2:
                # We apply this by capping the final score result later, or adding a heavy penalty now
                # Capping it here ensures it's shown in the Layer 3 breakdown
                # Update documentation text only as requested
                # [V12.7 RECALIBRATION] Reduced from -20 to -15 to prevent excessive score suppression
                reasons.append({"text": "Phantom Volume: Score capped at 70 when RVOL < 1.2", "type": "negative", "impact": -15.0, "layer": 3})
            
            intermediate_score = sum(r.get('impact', 0) for r in reasons if r["layer"] < 3)
            if intermediate_score > 75 and vol_ratio < 1.5:
                # Keep existing Phantom Volume penalty unchanged
                reasons.append({"text": "PHANTOM: Weak RVOL for High Score", "type": "negative", "impact": -10.0, "layer": 3})

            # [V12.7] Time Decay Factor
            if self.SCORING_FLAGS["enable_time_decay"]:
                # FIX START: Time Decay Logic Accuracy (Peak discovery for stale signal detection)
                if len(df_15m) >= 4:
                    # [V12.7] Relaxed Decay: Only trigger if truly failing to hold recent levels
                    recent_avg_high = df_15m['high'].iloc[-4:-1].mean()
                    if df_15m['close'].iloc[-1] < recent_avg_high * 0.998:
                        reasons.append({"text": "DECAY: Signal Stale (>3 Candles)", "type": "negative", "impact": -5.0, "layer": 3})
                # FIX END

            # [V12.7] Multi-Timeframe Confirmation (+5.0 Bonus) moved to Layer 2

            # Time Decay Logic

            # --- FINAL TRUTH CALCULATION ---
            # FIX START: Explicit Layer-Based Final Score Calculation (Ensures audit transparency)
            layer1 = sum(r.get('impact', 0) for r in reasons if r.get('layer') == 1)
            layer2 = sum(r.get('impact', 0) for r in reasons if r.get('layer') == 2)
            layer3 = sum(r.get('impact', 0) for r in reasons if r.get('layer') == 3)

            final_raw = layer1 + layer2 + layer3  # layer3 already contains negative values
            # FIX END
            # Final Score = Max(0, Min(100, (DNA + Alpha Edge) - Safeguards))
            # (Note: reasons list contains all impacts, so sum is correct as long as safeguards are negative)
            # FIX START: Ensure score clamping
            final_score = round(max(0, min(100, final_raw)), 1)
            # FIX END
            
            # [V12.7] Phantom Volume Score Cap (Final Enforcer)
            # FIX START: Ensure phantom volume cap is preserved
            if self.SCORING_FLAGS["enable_phantom_pre_filter"] and vol_ratio < 1.2:
                final_score = min(final_score, 70.0)
            # FIX END
            
            # Strict Institutional Thresholds
            # NEW LOGIC START: Dynamic DNA Gate (Prevent weak base trades from catching Alpha tails)
            dna_threshold = 15.0 if (self.SCORING_FLAGS.get("enable_dynamic_dna") and dna_mode == "RELAXED") else 20.0
            layer1_score = vw_impact + adx_impact + pa_impact + vol_impact
            
            if self.SCORING_FLAGS.get("enable_dna_gate"):
                if layer1_score < dna_threshold:
                    final_score = min(final_score, 59.9) # Prevent BUY signal if DNA is unreliable
            # NEW LOGIC END

            if   final_score >= 60: sig = "BUY"
            elif final_score >= 40: sig = "NEUTRAL"
            else: sig = "IGNORE"

            # 3. BUILD UI GROUPS [RESTORED]
            groups = {
                "DNA (40%)": {
                    "score": round(vw_impact + adx_impact + pa_impact + vol_impact, 1),
                    "max": 40,
                    "details": [r for r in reasons if r["layer"] == 1]
                },
                "Alpha Edge (60%)": {
                    "score": round(pioneer_bonus + sm_impact + inst_vol_impact + mtf_impact + timing_impact, 1),
                    "max": 60,
                    "details": [r for r in reasons if r["layer"] == 2]
                },
                "Safeguards (L3)": {
                    "score": round(sum(r.get('impact', 0) for r in reasons if r["layer"] == 3), 1),
                    "max": 0, # Penalties are subtractive
                    "details": [r for r in reasons if r["layer"] == 3]
                }
            }

            return {
                "symbol": sym, 
                "price": round(real_price, 2), 
                "score": final_score,
                "signal": sig, 
                "signal_label": f"{sig} {('🏆' if final_score > 85 else '✅')}", 
                "verdict": "👑 PIONEER PRIME [ULTRA CONVICTION]" if final_score >= 85 else "Standard Institutional Setup",
                "reasons": reasons,
                "groups": groups,
                "weights": {"DNA": 40, "Institutional": 60},
                "entry": round(real_price, 2),
                "target": round(target_p, 2),
                "stop_loss": round(sl_p, 2),
                "expected_hike": round(hike_pct, 2),
                "dna_mode": dna_mode if self.SCORING_FLAGS.get("debug_dna_mode") else None,
                "alpha_mode": alpha_mode if self.SCORING_FLAGS.get("debug_alpha_mode") else None
            }
        except Exception as e:
            return {"symbol": sym, "skip_reason": f"Restoration Error: {str(e)}"}

    async def run_scan(self, job_id: str, logger=None):
        """[V10 SPEED] Pulse-Fire Main Loop with [V11 TIMEOUT PROTECTION]."""
        from app.services.market_discovery import market_discovery
        symbols = await market_discovery.get_full_market_list()
        if not symbols: return {"status": "error"}

        total = len(symbols)
        print(f"🛰️ [V11 RESTORED] Pulse Scan: {total} symbols")
        
        self.job_states[job_id] = {"results": [], "failed_symbols": [], "progress": 0, "is_running": True, "pause_requested": False, "main_task": asyncio.current_task()}
        index_ctx = await self._get_index_context()
        sync_task = asyncio.create_task(self._progress_loop(job_id, total))

        try:
            # Process in Streaming Batches of 100
            chunk_size = 100
            for i in range(0, total, chunk_size):
                # [V12.1 STOP CHECK] 🛑
                if job_id in self.job_states and not self.job_states[job_id].get("is_running", True):
                    if logger: logger.warning(f"🛑 [INTRA] Stop Signal Received. Terminating job {job_id} at {i}/{total}.")
                    break

                # [V12.1 PAUSE CHECK] ⏸️
                while job_id in self.job_states and self.job_states[job_id].get("pause_requested"):
                    if not self.job_states[job_id].get("is_running", True): break
                    await asyncio.sleep(1)

                chunk = symbols[i:i + chunk_size]
                chunk_syms = [s["symbol"] if isinstance(s, dict) else s for s in chunk]
                
                print(f"🛰️ Pulse Batch: {i}/{total} ({len(chunk_syms)} symbols)")
                
                # 1. Fetch data for this specific batch (with 30s HARD TIMEOUT)
                try:
                    res_15m, res_prices = await asyncio.wait_for(
                        asyncio.gather(
                            market_service.get_batch_ohlc(chunk_syms),
                            market_service.get_batch_prices(chunk_syms)
                        ),
                        timeout=120.0
                    )
                except asyncio.TimeoutError:
                    print(f"⚠️ [V11 TIMEOUT] Batch {i} hung. Force-skipping to maintain engine flow.")
                    self.job_states[job_id]["progress"] += len(chunk)
                    continue

                batch_pulse = {}
                for s in chunk_syms:
                    batch_pulse[s] = {"15m": res_15m.get(s), "price": res_prices.get(s, {}).get("price", 0.0)}

                # 2. Analyze the batch immediately
                async def sem_task(s_obj):
                    sym = s_obj["symbol"] if isinstance(s_obj, dict) else s_obj
                    async with self.semaphore:
                        try:
                            # [PER-STOCK LOGGING REQUESTED]
                            res = await asyncio.wait_for(
                                self.analyze_stock(sym, job_id, index_ctx, batch_pulse),
                                timeout=10.0
                            )
                            
                            if res and "skip_reason" not in res: 
                                self.job_states[job_id]["results"].append(res)
                                if logger:
                                    # [V12.7 HIGH-TRANSPARENCY LOGGER] 🔍
                                    l1 = res.get("groups", {}).get("DNA (40%)", {}).get("score", 0)
                                    l2 = res.get("groups", {}).get("Alpha Edge (60%)", {}).get("score", 0)
                                    l3 = res.get("groups", {}).get("Safeguards (L3)", {}).get("score", 0)
                                    
                                    reasons = res.get("reasons", [])
                                    catalysts = [r["text"] for r in reasons if r.get("impact", 0) > 0 and r.get("layer") in [1, 2]]
                                    penalties = [r["text"] for r in reasons if r.get("impact", 0) < 0 and r.get("layer") == 3]
                                    
                                    logger.info(f"✅ {sym}: {res['score']:>5} | [L1:{l1:>4} | L2:{l2:>4} | L3:{l3:>5}] | {res['signal']} ({res.get('alpha_mode', 'NONE')})")
                                    if catalysts: logger.info(f"   └ 🚀 Catalysts: {', '.join(catalysts[:4])}")
                                    if penalties: logger.info(f"   └ 🛡️ Penalties: {', '.join(penalties[:4])}")
                            else:
                                if logger: logger.warning(f"⚠️ {sym}: Skipped. Reason: {res.get('skip_reason', 'Unknown')}")
                        except Exception as e:
                            if logger: logger.error(f"❌ {sym}: Analysis ERROR: {str(e)}")
                            pass
                        finally:
                            self.job_states[job_id]["progress"] += 1

                await asyncio.gather(*[sem_task(s) for s in chunk])
                
        finally:
            self.job_states[job_id]["is_running"] = False
            await sync_task

        results = sorted(self.job_states[job_id]["results"], key=lambda x: x["score"], reverse=True)
        return sanitize_data({"total": total, "success": len(results), "data": results})

    async def stop_job(self, job_id: str):
        """[V12.1 RESTORED] Programmatic termination signal."""
        if job_id in self.job_states:
            self.job_states[job_id]["is_running"] = False
            print(f"🛑 Signal sent to stop job {job_id}")

    async def pause_job(self, job_id: str):
        """[V12.1] Pause terminal signal."""
        if job_id in self.job_states:
            self.job_states[job_id]["pause_requested"] = True
            print(f"⏸️ Signal sent to pause job {job_id}")

    async def resume_job(self, job_id: str):
        """[V12.1] Resume terminal signal."""
        if job_id in self.job_states:
            self.job_states[job_id]["pause_requested"] = False
            print(f"▶️ Signal sent to resume job {job_id}")

    async def _progress_loop(self, job_id: str, total: int):
        while job_id in self.job_states and self.job_states[job_id]["is_running"]:
            try:
                state = self.job_states[job_id]
                async with AsyncSessionLocal() as session:
                    job = await session.get(Job, job_id)
                    if job:
                        # [V12.1 EXTERNAL CANCEL CHECK] 🛑
                        if job.status in ["failed", "cancelled", "stopped"]:
                            state["is_running"] = False
                            # [V12.2] Explicitly cancel the main execution task
                            main_task = state.get("main_task")
                            if main_task and not main_task.done():
                                main_task.cancel()
                            break
                        
                        # [V12.1 EXTERNAL PAUSE CHECK] ⏸️
                        if job.status == "paused":
                            state["pause_requested"] = True
                        elif state.get("pause_requested") and job.status == "processing":
                            state["pause_requested"] = False

                        job.result = sanitize_data({
                            "progress": state["progress"], "total_steps": total,
                            "data": sorted(state["results"], key=lambda x: x["score"], reverse=True)[:100],
                            "status_msg": f"V11 Pulse Scan: {state['progress']}/{total}"
                        })
                        flag_modified(job, "result")
                        await session.commit()
            except: pass
            await asyncio.sleep(2.5)

intraday_engine = IntradayEngine()
