
import asyncio
import time
import pandas as pd
from datetime import datetime
from app.services.market_data import market_service
from app.services.ta_longterm import ta_longterm
from app.services.fundamentals import fundamental_engine
from app.services.risk_sentiment import risk_engine
from app.services.sector_engine import sector_engine
from app.services.advisor_engine import advisor_engine
from app.models.job import Job
from app.db.session import AsyncSessionLocal
from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified

from app.services.utils import STATIC_FULL_LIST, sanitize_data
from app.services.market_discovery import market_discovery

class ScannerEngine:
    def __init__(self):
        self.running = False
        self.delay = 0.5 
        self.semaphore = asyncio.Semaphore(20)
        self.active_symbols = [] 
        self.results_buffer = [] 
        self.progress_counter = 0 
        self.scan_active = False 
        self.sector_counts = {} # Sector frequency tracking for Portfolio Awareness
        self.job_states = {} # Track concurrent jobs
    @staticmethod
    def sanitize(data):
        return sanitize_data(data)
    
    async def run_scan(self, job_id, mode="full"):
        """
        Main entry point for a Job.
        Returns the result dict.
        """
        print(f"Engine: Starting Scan for Job {job_id} [{mode}]")
        
        # 1. Get Symbols
        symbols = []
        if mode in ["full", "full_scan", "longterm"]:
            try:
                # 1. Try Professional Discovery (NSE 2000+)
                symbols = await market_discovery.get_full_market_list()
                if symbols:
                    print(f"Engine: Discovered {len(symbols)} stocks from Full NSE Market.")
                
                # 2. Fallback to Nifty 500 JSON if discovery fails
                if not symbols:
                    import json
                    import os
                    json_path = os.path.join("app", "data", "nifty500.json")
                    if os.path.exists(json_path):
                        with open(json_path, "r") as f:
                            symbols = json.load(f)
                            print(f"Loaded {len(symbols)} symbols from nifty500.json")
            except Exception as e:
                print(f"Error resolving symbols for {mode}: {e}")
            
            if not symbols:
                symbols = STATIC_FULL_LIST # Fallback
        
        # 2. Randomize The List (User Request)
        # Ensures that even if the scan stops halfway or we limit it, we get a fresh variety.
        import random
        random.shuffle(symbols)
        print(f"Randomized Scan Order. First 5: {symbols[:5]}")
        
        # 2. Iterate
        results = []
        errors = []
        
        total = len(symbols)
        
        # 1. Reset State
        self.active_symbols = []
        self.results_buffer = []
        self.progress_counter = 0
        self.scan_active = True

        # 2. Initial Progress Update & Start Background Sync
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(Job).where(Job.id == job_id)
                res = await session.execute(stmt)
                job_obj = res.scalars().first()
                if job_obj:
                    job_obj.result = {"progress": 0, "total_steps": total, "status_msg": "Initializing Scan..."}
                    flag_modified(job_obj, "result")
                    await session.commit()
        except Exception as e: print(f"Init progress fail: {e}")

        # 2.5 Market Regime Detection (Phase 33)
        regime = await self._detect_market_regime()
        macro = await self._detect_macro_regime()
        print(f"Engine: Regime [{regime['label'].upper()}] | Macro [{macro['label'].upper()}]")
        weights = regime["weights"]

        # Start background sync with per-job state isolation
        self.job_states[job_id] = {
            "results": [],
            "active": [],
            "progress": 0,
            "is_running": True
        }
        sync_task = asyncio.create_task(self._progress_loop(job_id, total))

        async def sem_task(sym, idx):
                async with self.semaphore:
                    state = self.job_states[job_id]
                    state["active"].append(sym)
                    try:
                        # 1. Check for Stop/Pause Signal
                        async with AsyncSessionLocal() as session:
                            q = select(Job).where(Job.id == job_id)
                            db_res = await session.execute(q)
                            job_obj = db_res.scalars().first()
                            if job_obj:
                                if job_obj.status == "stopped":
                                    print(f"🛑 Engine: Stop Signal received for {sym}. Aborting task.")
                                    return
                                
                                while job_obj.status == "paused":
                                    await asyncio.sleep(2)
                                    await session.refresh(job_obj)
                                    if job_obj.status == "stopped": return

                        # 2. Strict Throttling for APIs per slot
                        await asyncio.sleep(self.delay)
                        
                        # 3. Fetch & Analyze
                        symbol_str = sym["symbol"] if isinstance(sym, dict) else sym
                        
                        print(f"[{idx+1}/{total}] Concurrent Logic Execution: {symbol_str}")
                        res = await self.analyze_stock(symbol_str, weights=weights, regime_label=regime['label'], macro_data=macro)
                        if res:
                            state["results"].append(res)
                            results.append(res)
                        
                        state["progress"] += 1
                    except Exception as e:
                        print(f"Error scanning {sym}: {e}")
                        errors.append(f"{sym}: {str(e)}")
                        state["progress"] += 1 
                    finally:
                        if sym in state["active"]:
                            state["active"].remove(sym)

        tasks = [sem_task(sym, i) for i, sym in enumerate(symbols)]
        await asyncio.gather(*tasks)

        # 2.5 Stop background sync and wait for it
        if job_id in self.job_states:
            self.job_states[job_id]["is_running"] = False
        await sync_task
        if job_id in self.job_states: del self.job_states[job_id]
                
        # 3. Sort & Filter (Prioritization Logic)
        # Sort by Final Score (Desc)
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        # 4. Return
        print(f"Scan Completed. Found {len(results)} valid signals.")
        final_payload = {
            "total_scanned": total,
            "success_count": len(results),
            "data": results,
            "errors": errors[:20], 
            "progress": total,
            "total_steps": total,
            "status_msg": "Completed"
        }
        return self.sanitize(final_payload)

    async def analyze_stock(self, sym, weights=None, regime_label="Standard", macro_data=None):
        """
        Single Stock Analysis - Robust Wrapper
        """
        # Default Weights (Standard)
        if weights is None:
            weights = {
                "fundamental": 0.40,
                "trend": 0.25,
                "momentum": 0.15,
                "volume": 0.10,
                "risk": 0.10
            }
        
        macro_adjustment = 0
        if macro_data:
            metadata = await market_service.get_symbol_metadata(sym)
            sector = metadata.get("sector", "Unknown")
            macro_adjustment = self._calculate_macro_adjustment(sector, macro_data)
        
        try:
            # 1. Fetch Data
            # Note: We use the existing market_service logic but throttled
            df = await market_service.get_ohlc(sym, period="5y", interval="1wk") # Long term scan (5y for 200 EMA accuracy)
            price_data = await market_service.get_live_price(sym)
            
            real_price = price_data.get("price", 0.0)
            market_cap = price_data.get("market_cap", 0.0)
            
            # Robust Check for NaN/None
            import numpy as np
            is_valid_price = real_price is not None and not (isinstance(real_price, float) and np.isnan(real_price)) and real_price > 0
            is_valid_df = not df.empty and len(df) > 20
             
            print(f"DEBUG: {sym} -> Price: {real_price} (Valid: {is_valid_price}), OHLC Rows: {len(df)} (Valid: {is_valid_df})")

            if not is_valid_df or not is_valid_price: 
                print(f"⚠️ [DEBUG] {sym}: Data Unavailable or Invalid (OHLC: {len(df)}, Price: {real_price})")
                return None

            # 2. TA Analysis
            ta_res = await asyncio.to_thread(ta_longterm.analyze_stock, df)
            if not ta_res: 
                print(f"⚠️ [DEBUG] {sym}: TA Analysis Failed")
                return None
            
            # 3. Fundamental/Risk Analysis (Phase 29: Historical Context)
            fund = await market_service.get_fundamentals(sym)
            metadata = await market_service.get_symbol_metadata(sym)
            sector_name = metadata.get("sector", "Unknown")
            
            # Parallel fetch for Efficiency (Phase 30: Sector Intel)
            index_df_task = asyncio.create_task(market_service.get_index_performance(sector_name))
            ext_task = asyncio.create_task(market_service.get_extended_data(sym))
            hist_fin_task = asyncio.create_task(market_service.get_historical_financials(sym))
            
            index_df = await index_df_task
            ext = await ext_task
            hist_financials = await hist_fin_task
            
            fund_res = await asyncio.to_thread(fundamental_engine.analyze, fund, hist_financials)
            risk_res = await asyncio.to_thread(risk_engine.analyze, ext, fund, df)
            sector_res = await asyncio.to_thread(sector_engine.analyze, df, index_df, sector_name)
            
            # --- PROFESSIONAL ADAPTIVE SCORING (Phase 33) ---
            fund_score = fund_res["score"]
            trend_score = ta_res.get("trend_score", 0)
            mom_score = ta_res.get("mom_score", 0)
            vol_score = risk_res.get("volume_score", 0)
            risk_stability_score = risk_res.get("stability_score", 0)
            
            # Sector Bonus/Penalty (Phase 30: Alpha Influence)
            sector_alpha = sector_res.get("alpha", 0)
            sector_adjustment = max(-5, min(5, sector_alpha * 20)) 
            
            # --- INSTITUTIONAL INTEL (Paid App Features) ---
            from app.services.institutional_intel import institutional_intel
            inst_data = await asyncio.to_thread(institutional_intel.analyze, df)
            
            inst_score = 0
            # 1. RS Rating Boost (MarketSmith Style)
            rs_rating = inst_data.get("rs_rating", 50)
            if rs_rating > 80: inst_score += 10
            elif rs_rating > 90: inst_score += 15
            
            # 2. VCP Pattern (Minervini)
            if inst_data.get("vcp_detected", False):
                inst_score += 15
                print(f"💎 VCP PATTERN DETECTED: {sym}")
                
            # 3. Sponsorship
            spon_action = inst_data.get("institutional_action", "Neutral")
            if "Accumulation" in spon_action: inst_score += 10
            elif "Distribution" in spon_action: inst_score -= 10

            final_score = (fund_score * weights["fundamental"]) + \
                          (trend_score * weights["trend"]) + \
                          (mom_score * weights["momentum"]) + \
                          (vol_score * weights["volume"]) + \
                          (risk_stability_score * weights["risk"]) + \
                          sector_adjustment + \
                          macro_adjustment + \
                          inst_score
            
            # --- BREAKOUT BOOST (Phase 62: Momentum Prioritization) ---
            # If stock is near 52-Week High AND has Volume Support -> Massive Boost
            is_near_high = ta_res.get("is_near_52w_high", False)
            rel_vol = risk_res.get("relative_volume", 1.0)
            
            if is_near_high and rel_vol > 1.5:
                # This is a Category A Breakout Candidate
                # We boost it to ensuring it bubbles up even if Fundamentals are average
                print(f"🚀 BREAKOUT DETECTED: {sym} (RelVol: {rel_vol})")
                final_score += 15 
            elif is_near_high:
                final_score += 5

            # Penalty for Low Momentum in Momentum Mode
            if weights["momentum"] > 0.3 and mom_score < 40:
                final_score -= 20 # Crush dead stocks in momentum scan

            final_score = round(final_score, 1)
            
            # 5. Extract Details for UI and Logic (Moved Up to avoid crash)
            ta_details = []
            if "groups" in ta_res:
                for g_val in ta_res["groups"].values():
                    ta_details.extend(g_val.get("details", []))
            
            fund_details = fund_res.get("details", [])
            risk_details = risk_res.get("details", [])
            sector_details = sector_res.get("details", [])
            
            # Combine all details for labels/logic
            all_reasons = ta_details + fund_details + risk_details + sector_details

            # --- GLOBAL CONTEXT INJECTION (Phase 36) ---
            # 1. Market Regime
            if "Bearish" in regime_label:
                all_reasons.append({
                    "text": "Structural Bear Market",
                    "type": "negative",
                    "label": "REGIME",
                    "value": "High Volatility Shift"
                })
            elif "Bullish" in regime_label:
                all_reasons.append({
                    "text": "Structural Bull Market",
                    "type": "positive",
                    "label": "REGIME",
                    "value": "Momentum Shift"
                })

            # 2. Macro Adjustments
            if macro_adjustment < 0:
                all_reasons.append({
                    "text": "Macro Resource Headwind",
                    "type": "negative",
                    "label": "MACRO",
                    "value": f"{round(macro_adjustment, 1)}pt Penalty"
                })
            elif macro_adjustment > 0:
                all_reasons.append({
                    "text": "Macro Sector Tailwinds",
                    "type": "positive",
                    "label": "MACRO",
                    "value": f"{round(macro_adjustment, 1)}pt Bonus"
                })
            
            # --- PROFESSIONAL STRICT DECISION ENGINE ---
            is_bullish = ta_res.get("is_bullish_trend", False)
            ema_val = ta_res.get("ema_200_val", 0)

            # Strict Thresholds (Phase 22)
            # Widen HOLD zone to prevent "Borderline" flips
            if final_score >= 65:
                if is_bullish:
                    signal = "BUY"
                else:
                    signal = "NEUTRAL" # Trend Guard
            elif final_score < 35:
                if not is_bullish:
                    signal = "SELL"
                else:
                    signal = "NEUTRAL" # Trend Guard
            else:
                signal = "NEUTRAL"

            # Strategic Summary Logic (Dynamic & Specific - Phase 15)
            # Prioritize 200 EMA Strategic Commentary (Phase 26)
            ema_advice = next((d["text"] for d in ta_details if "200 EMA" in d.get("label", "")), None)
            ema_target = next((d["text"] for d in ta_details if "Possible Price" in d.get("text", "")), None)
            ema_trend = next((d["text"] for d in ta_details if "TREND" in d.get("label", "")), None)
            
            positives = [d["text"] for d in all_reasons if d.get("type") == "positive"]
            negatives = [d["text"] for d in all_reasons if d.get("type") == "negative"]
            
            # Prioritize based on signal (Phase 36)
            if signal == "SELL":
                top_pros = positives[:1] # Fewer pros
                risk_warn = negatives[0] if negatives else "structural momentum breakdown"
                pro_context = f"limited by {risk_warn}"
            elif signal == "NEUTRAL":
                top_pros = positives[:2]
                risk_warn = negatives[0] if negatives else "lack of clear catalysts"
                pro_context = f"balanced between strengths and {risk_warn}"
            else:
                top_pros = positives[:2]
                risk_warn = negatives[0] if negatives else "no major structural risks"
                pro_context = f"driven by {', '.join(top_pros)}" if top_pros else "aligned technical and fundamental indicators"

            # Category Rationale Logic (Phase 19 & 22 & 26)
            rationale = ""
            if ema_advice:
                # If near 200 EMA, force it into the rationale
                ema_val_str = next((d["value"] for d in ta_details if "LEVEL" in d.get("label", "")), "target")
                rationale = f"Strategically positioned near 200 EMA ({ema_val_str}). {ema_advice}. {ema_trend}."
            elif signal == "BUY":
                rationale = f"Assigned to BUY because {top_pros[0] if top_pros else 'strong metrics'} are aligned with a Bullish Trend."
            elif signal == "NEUTRAL":
                if final_score >= 65 and not is_bullish:
                    rationale = f"HELD (Guard Triggered): High Score ({final_score}) is currently waiting for Trend Confirmation (Price < {round(ema_val,1)})."
                elif final_score < 35 and is_bullish:
                    rationale = f"HELD (Guard Triggered): Weak Score ({final_score}) is being supported by Trend (Price > {round(ema_val,1)})."
                elif positives and negatives:
                    rationale = f"Assigned to HOLD because {positives[0]} is currently neutralized by {negatives[0]}."
                else:
                    rationale = "Assigned to HOLD due to mixed data and lack of clear directional conviction."
            else:
                rationale = f"Assigned to SELL due to {risk_warn} aligned with a Bearish breakdown."

            verdict = ""
            if ema_advice:
                ema_val_str = next((d["value"] for d in ta_details if "LEVEL" in d.get("label", "")), "target")
                verdict = f"{ema_advice} at {ema_val_str}. {ema_trend}."
            
            # Phase 33: Moat & Recovery Context in Verdict
            moat_score = fund_res.get("moat_score", 0)
            recovery = ta_res.get("recovery", {}).get("label", "Moderate")
            if moat_score > 7:
                verdict += f" High pricing power (Stable Margins) suggests a strong competitive moat."
            if recovery == "Fast":
                verdict += f" Rapid historical recovery from drops confirms underlying institutional support."

            if not verdict:
                if final_score >= 75:
                    verdict = f"Exceptional {signal} conviction. {pro_context.capitalize()}."
                elif signal == "NEUTRAL":
                    verdict = f"Consolidation likely. {top_pros[0] if top_pros else 'Stable metrics'} countered by {risk_warn}. Wait and watch."
                elif fund_score > 70:
                    verdict = f"Strong fundamentals ({', '.join(top_pros) if top_pros else 'Value/Quality'}) provide a safety margin despite technical weakness."
                elif trend_score > 70:
                    verdict = f"Technical momentum ({', '.join(top_pros) if top_pros else 'Trend Strength'}) is overriding short-term fundamental concerns."
                else:
                    verdict = f"Balanced {signal} signal. {top_pros[0] if top_pros else 'Diversified metrics'} countered by {risk_warn}."
            
            # --- FINAL REASON PRIORITIZATION (Phase 36) ---
            # 1. EMA Priority (Phase 26) - Ensure EMA logic is first in the pool if advice exists
            pool = all_reasons
            if ema_advice:
                 ema_items = [d for d in pool if any(k in d.get("label", "") for k in ["200 EMA", "LEVEL", "TREND", "ACTION"])]
                 other_items = [d for d in pool if d not in ema_items]
                 pool = ema_items + other_items

            # 2. Signal-Aware TOP 5 (Phase 36)
            positives_objs = [r for r in pool if r.get("type") == "positive"]
            negatives_objs = [r for r in pool if r.get("type") == "negative"]
            
            if signal == "SELL":
                # ABSOLUTE PRIORITY for Negatives on SELL
                top_reasons = (negatives_objs + positives_objs)[:5]
            elif signal == "NEUTRAL" and final_score < 50:
                # Prioritize Risks if score is below 50 even if HELD
                top_reasons = (negatives_objs + positives_objs)[:5]
            else:
                top_reasons = (positives_objs + negatives_objs)[:5]

            # Additional logic to clarify Beta in the details if it exists
            # ... (rest of Beta logic)
            # (Note: I'll include the Beta logic in the replacement to avoid breaking it)
            for detail in risk_details:
                if "Beta" in detail.get("value", ""):
                    try:
                        b_val = float(detail["value"].split(":")[1].strip())
                        if b_val < 0.5:
                            detail["text"] = "Exceptional Market Stability"
                            detail["value"] = f"Moves only {round(b_val, 2)}x per 1% Market swing"
                        elif b_val > 1.5:
                            detail["text"] = "High Market Sensitivity"
                            detail["value"] = f"Aggressive: Moves {round(b_val, 2)}x with Market"
                    except: pass
            
            # --- PHASE 52: Dynamic Metadata ---
            metadata = await market_service.get_symbol_metadata(sym)
            sector_name = metadata.get("sector", "Services")
            cap_cat = metadata.get("market_cap_category", "Small")
            market_cap = metadata.get("market_cap_value", 0)
            
            # Key Levels & Reason
            target_val = ta_res.get("resistance", real_price * 1.05)
            stop_loss_val = ta_res.get("support", real_price * 0.95)
            target_reason = ta_res.get("target_reason", "Standard 5% Target")

            # --- INVESTMENT ADVISOR ENGINE (Phase 40) ---
            self.sector_counts[sector_name] = self.sector_counts.get(sector_name, 0) + 1
            portfolio_ctx = {"sector_distribution": self.sector_counts}

            advisory = advisor_engine.generate_advice(
                sym, real_price, fund_res, ta_res, risk_res, sector_res, portfolio_ctx, mode="longterm"
            )

            # Update Verdict with Advisor Context
            holding = {}
            targets = {}
            if advisory:
                holding = advisory.get("holding_period", {})
                targets = advisory.get("targets", {})
                play = holding.get("play_type", "Standard")
                period = holding.get('period_display', '3-5 Years')
                
                # Special Highlight for Short-Term "High Potential" plays
                if "Momentum" in holding.get('label', '') or "High-Potential" in play:
                    verdict += f" [🔥 MOMENTUM] {play}. HIGH potential indicated over {period}. Target: ₹{targets.get('3_year_target')} ({targets.get('projected_cagr')}% expected ROI)."
                elif "suggested hold" not in verdict.lower():
                    verdict += f" [Advisor] {play} Play. Suggested hold: {period}. Target: ₹{targets.get('3_year_target')} ({targets.get('projected_cagr')}% expected ROI)."
                
                # Add Smart Entry Rationale
                entry_analysis = advisory.get("entry_analysis", {})
                if entry_analysis:
                    verdict += f" [💡 ENTRY] {entry_analysis.get('rationale')}"

            return {
                "symbol": sym,
                "score": final_score,
                "signal": signal,
                "price": real_price,
                "analysis_mode": "LONGTERM_INVEST",
                "entry": advisory.get("entry_analysis", {}).get("entry_price", real_price) if advisory else real_price,
                "market_cap_category": cap_cat, 
                "market_cap_value": market_cap,
                "sector": sector_name, 
                "target": targets.get("3_year_target", target_val) if advisory else target_val,
                "stop_loss": advisory.get("stop_loss", {}).get("stop_price", stop_loss_val) if advisory else stop_loss_val,
                "target_reason": targets.get("blend_logic", target_reason) if advisory else target_reason,
                "levels": ta_res.get("levels", {}),
                "strategic_summary": verdict,
                "category_rationale": rationale,
                "accumulation_status": risk_res.get("accumulation_label", "Neutral"),
                "intrinsic_value": fund_res.get("intrinsic_value", 0),
                "valuation_gap": fund_res.get("valuation_gap", 0),
                "squeeze": ta_res.get("squeeze", {}),
                "investment_advisory": advisory,
                "weights": {
                    "Fundamental": int(weights["fundamental"] * 100),
                    "Technical (Trend)": int(weights["trend"] * 100),
                    "Technical (Momentum)": int(weights["momentum"] * 100),
                    "Volume Behavior": int(weights["volume"] * 100),
                    "Risk & Stability": int(weights["risk"] * 100),
                    "regime": regime_label
                },
                "reasons": top_reasons, 
                "groups": {
                    "Fundamental": {
                        "score": fund_score, 
                        "details": fund_details,
                        "status": "STRONG" if fund_score >= 50 else "WEAK"
                    },
                    "Technical (Trend)": {
                        "score": trend_score,
                        "details": ta_res.get("groups", {}).get("Trend", {}).get("details", []),
                        "status": "BULLISH" if trend_score >= 50 else "BEARISH"
                    },
                    "Technical (Momentum)": {
                        "score": mom_score,
                        "details": ta_res.get("groups", {}).get("Momentum", {}).get("details", []),
                        "status": "HIGH" if mom_score >= 50 else "LOW"
                    },
                    "Volume Behavior": {
                        "score": vol_score,
                        "details": [d for d in risk_res.get("details", []) if d.get("label") in ["ACC", "VOL", "EXIT"]],
                        "status": "ACTIVE" if vol_score >= 50 else "QUIET"
                    },
                    "Risk & Stability": {
                        "score": risk_stability_score,
                        "details": [d for d in risk_res.get("details", []) if d.get("label") in ["SAFE", "RISK", "SEC", "VIX"]],
                        "status": "STABLE" if risk_stability_score >= 50 else "VOLATILE"
                    },
                    "Strategic Alpha": {
                        "score": round(sector_res.get("score", 5.0) * 10, 1),
                        "details": sector_res.get("details", []),
                        "status": sector_res.get("relative_strength", "Neutral").upper()
                    }
                },
                "alpha_intel": {
                    "quality_score": round(fund_score, 1),
                    "growth_probability": "High" if (mom_score > 60 and sector_alpha > 0) else "Medium",
                    "risk_level": risk_res.get("risk_level", "Medium"),
                    "valuation_status": "Slightly Expensive" if fund_res.get("valuation_gap", 0) < -15 else "Attractive",
                    "suggested_hold": advisory.get("holding_period", {}).get("period_display", "3-5 Years") if advisory else "3-5 Years",
                    "confidence": f"{final_score}%",
                    "moat_status": "Wide" if moat_score > 7 else "Narrow" if moat_score < 3 else "Stable",
                    "recovery_vibe": recovery
                }
            }

        except Exception as e:
            import traceback
            print(f"❌ Error analyzing {sym}: {e}")
            traceback.print_exc()
            return None

    async def _progress_loop(self, job_id, total):
        """
        Single Background Task to sync progress.
        Prevents multiple concurrent DB writes and SQLite locks.
        """
        print(f"📡 Progress Sync Loop started for Job {job_id}")
        while job_id in self.job_states and self.job_states[job_id].get("is_running"):
            try:
                state = self.job_states.get(job_id)
                if not state: break
                
                async with AsyncSessionLocal() as session:
                    stmt = select(Job).where(Job.id == job_id)
                    res = await session.execute(stmt)
                    job_obj = res.scalars().first()
                    if job_obj:
                        # Normalize active_symbols for display (ensure string join)
                        display_symbols = [s["symbol"] if isinstance(s, dict) else s for s in state["active"]]
                        
                        active_str = ", ".join(display_symbols[:3])
                        if len(display_symbols) > 3:
                            active_str += f" and {len(display_symbols)-3} others"
                        
                        current_result = job_obj.result or {}
                        if not isinstance(current_result, dict): current_result = {}
                        
                        current_result["progress"] = state["progress"]
                        current_result["total_steps"] = total
                        current_result["active_symbols"] = display_symbols
                        
                        # INCREMENTAL PERSISTENCE (Save data every pulse)
                        current_result["data"] = list(state["results"])
                        
                        # Status message based on job state
                        if job_obj.status == "paused":
                            current_result["status_msg"] = f"PAUSED: {active_str}"
                        elif job_obj.status == "stopped":
                            current_result["status_msg"] = "STOPPED (Partial results saved)"
                            state["is_running"] = False # Kill loop
                        else:
                            current_result["status_msg"] = f"Analyzing: {active_str}"
                        
                        job_obj.result = self.sanitize(current_result)
                        flag_modified(job_obj, "result")
                        job_obj.updated_at = datetime.utcnow()
                        await session.commit()
            except Exception as e:
                print(f"Progress Sync Warning for {job_id}: {e}")
            
            # Update every 2 seconds
            await asyncio.sleep(2.0)
        
        # Final update to 100% or whatever state we reached
        try:
             async with AsyncSessionLocal() as session:
                stmt = select(Job).where(Job.id == job_id)
                res = await session.execute(stmt)
                job_obj = res.scalars().first()
                if job_obj:
                    state = self.job_states.get(job_id, {"progress": total})
                    current_result = job_obj.result or {}
                    current_result["progress"] = state["progress"]
                    job_obj.result = self.sanitize(current_result)
                    flag_modified(job_obj, "result")
                    await session.commit()
        except: pass
        print(f"📡 Progress Sync Loop stopped for Job {job_id}")

    async def _detect_market_regime(self) -> dict:
        """
        Detects Market Regime using Nifty & VIX (Phase 33).
        Returns weights for the session.
        """
        try:
            status = await market_service.get_market_status()
            vix = status.get("india_vix", 15)
            nifty = status.get("nifty_50", 0)
            
            # Simple Bear/Bull Check
            # In a real app, we'd compare Nifty to its 200 EMA here.
            # For now, we use VIX as the primary proxy.
            
            if vix > 22:
                # BEAR/CRASH Regime: Focus on Cash & Quality
                return {
                    "label": "Bearish (High Volatility)",
                    "weights": {
                        "fundamental": 0.50, "trend": 0.15, "momentum": 0.05, "volume": 0.15, "risk": 0.15
                    }
                }
            elif vix < 15:
                # BULL Regime: Focus on Momentum & Trend
                return {
                    "label": "Bullish (Gaining Momentum)",
                    "weights": {
                        "fundamental": 0.30, "trend": 0.35, "momentum": 0.20, "volume": 0.10, "risk": 0.05
                    }
                }
            else:
                return {
                    "label": "Standard (Neutral)",
                    "weights": {
                        "fundamental": 0.40, "trend": 0.25, "momentum": 0.15, "volume": 0.10, "risk": 0.10
                    }
                }
        except:
            return {
                "label": "Standard (Fallback)",
                "weights": {
                    "fundamental": 0.40, "trend": 0.25, "momentum": 0.15, "volume": 0.10, "risk": 0.10
                }
            }

    async def _detect_macro_regime(self) -> dict:
        """
        Analyzes Global Macro Indicators (Phase 34).
        """
        try:
            # Fetch Crude and USDINR
            import yfinance as yf
            crude = await asyncio.to_thread(lambda: yf.Ticker("CL=F").history(period="5d")['Close'].iloc[-1])
            currency = await asyncio.to_thread(lambda: yf.Ticker("INR=X").history(period="5d")['Close'].iloc[-1])
            
            label = "Macro Normal"
            if crude > 90: label = "High Crude (Energy Headwinds)"
            elif crude < 65: label = "Low Crude (Fuel Tailwinds)"
            
            if currency > 83.5: label += " | Weak INR (Export Advantage)"
            
            return {"label": label, "crude": crude, "currency": currency}
        except:
            return {"label": "Macro Normal (Fallback)", "crude": 75, "currency": 83}

    def _calculate_macro_adjustment(self, sector: str, macro: dict) -> float:
        """
        Applies sector-specific adjustments based on macro regime.
        """
        adj = 0.0
        crude = macro.get("crude", 75)
        currency = macro.get("currency", 83)
        
        # 1. Crude Impact
        if crude > 90: # High Crude
            if sector in ["Energy"]: adj += 3.0
            if sector in ["FMCG", "Auto", "Pharma"]: adj -= 2.0 # Raw material costs
        elif crude < 65: # Low Crude
            if sector in ["FMCG", "Auto"]: adj += 2.0
            
        # 2. Currency Impact
        if currency > 83.5: # Weak INR
            if sector in ["IT", "Pharma"]: adj += 3.0 # Export revenue increase
            if sector in ["Infrastructure"]: adj -= 2.0 # Import costs (machinery/debt)
            
        return adj

scanner_engine = ScannerEngine()
