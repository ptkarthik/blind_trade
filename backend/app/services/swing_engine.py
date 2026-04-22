import asyncio
import time
import random
from typing import Dict, Any, List
import pandas as pd
import logging
from datetime import datetime

from app.services.market_data import market_service
from app.services.market_discovery import market_discovery
from app.services.ta_swing import ta_swing, safe_scalar
from app.services.portfolio_engine import portfolio_engine
from app.services.trade_manager import trade_manager
from app.services.utils import sanitize_data

logger = logging.getLogger(__name__)

class SwingEngine:
    def __init__(self):
        self.job_states = {} # { job_id: {"progress": int, "total_steps": int, "results": list, "failed_symbols": list, "status_msg": str} }
        self.market_context = {"nifty_bullish": False, "nifty_sma50": 0, "nifty_price": 0}

    def start_job(self, job_id: str):
        self.job_states[job_id] = {
            "progress": 0,
            "total_steps": 1, 
            "results": [],
            "failed_symbols": [],
            "errors": [],
            "status_msg": "Initializing market-adaptive swing scan...",
            "active_symbols": [],
            "target_count": 0,
            "stop_requested": False,
            "pause_requested": False,
            "is_running": True,
            "last_data_sync": 0,
            "last_sync_time": time.time()
        }

    def update_job_progress(self, job_id: str, new_progress: int, total_steps: int = None, status_msg: str = None, active_symbols: list = None):
        if job_id not in self.job_states: return
        state = self.job_states[job_id]
        if status_msg is not None: state["status_msg"] = status_msg
        if active_symbols is not None: state["active_symbols"] = active_symbols
        safe_progress = min(new_progress, state.get("total_steps", new_progress))
        if safe_progress < state["progress"]: safe_progress = state["progress"]
        state["progress"] = safe_progress
        if total_steps is not None: state["total_steps"] = total_steps
             
    def add_job_result(self, job_id: str, result: dict):
        if job_id in self.job_states:
             if not any(r["symbol"] == result["symbol"] for r in self.job_states[job_id]["results"]):
                 self.job_states[job_id]["results"].append(result)

    def add_failed_symbol(self, job_id: str, symbol_info: dict):
        if job_id in self.job_states:
            self.job_states[job_id]["failed_symbols"].append(symbol_info)

    async def refresh_market_context(self):
        """Fetch NIFTY 50 trend to set the global strategy bias."""
        try:
            # V2 Evasion: Use NIFTYBEES.NS to bypass the ^NSEI Yahoo rate limits via jugaad_data
            df_nifty = await self._fetch_swing_ohlc_with_evasion("NIFTYBEES.NS", period="1y", interval="1d")
            if df_nifty is not None and not df_nifty.empty and len(df_nifty) > 50:
                from ta.trend import SMAIndicator
                sma50_series = SMAIndicator(close=df_nifty['close'], window=50).sma_indicator()
                nifty_price = safe_scalar(df_nifty['close'].iloc[-1])
                nifty_sma50 = safe_scalar(sma50_series.iloc[-1])
                nifty_20d_price = safe_scalar(df_nifty['close'].iloc[-21])
                nifty_20d_return = ((nifty_price / nifty_20d_price) - 1) * 100 if nifty_20d_price > 0 else 0
                
                from ta.momentum import RSIIndicator
                nifty_rsi = safe_scalar(RSIIndicator(close=df_nifty['close'], window=14).rsi().iloc[-1])
                
                self.market_context = {
                    "nifty_bullish": nifty_price > nifty_sma50,
                    "nifty_sma50": nifty_sma50,
                    "nifty_price": nifty_price,
                    "nifty_rsi": nifty_rsi,
                    "nifty_exhausted": nifty_rsi > 75,
                    "nifty_20d_return": nifty_20d_return,
                    "nifty_change": nifty_price - safe_scalar(df_nifty['close'].iloc[-2])
                }
                logger.info(f"📊 Market Context: NIFTY {'Bullish' if self.market_context['nifty_bullish'] else 'Bearish'} (RSI: {round(nifty_rsi, 1)})")
        except Exception as e:
            logger.error(f"Failed to refresh market context: {e}")

        try:
            sector_perf = await market_service.get_sector_performances()
            self.market_context["sector_performance"] = sector_perf
            logger.info("🗺️ Sector Heatmap Refreshed.")
        except Exception as e:
            self.market_context["sector_performance"] = {}
            logger.error(f"Failed to fetch sector performance: {e}")

        try:
            ad_ratio = await market_service.get_advance_decline_ratio()
            self.market_context["ad_ratio"] = ad_ratio
            logger.info(f"⚖️ Market Breadth (A/D Ratio): {round(ad_ratio, 2)}")
        except Exception as e:
            self.market_context["ad_ratio"] = 1.0
            logger.error(f"Failed to fetch A/D ratio: {e}")

    async def _fetch_swing_ohlc_with_evasion(self, sym: str, period: str = "1y", interval: str = "1d"):
        """Isolated Anti-Ban Fetcher specifically for Swing. Never returns None — always tries direct as final fallback."""
        import yfinance as yf
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        USER_AGENTS = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.2365.92"
        ]

        def _make_session(ua: str):
            s = requests.Session()
            s.verify = True
            s.headers.update({"User-Agent": ua, "Accept": "*/*", "Connection": "close"})
            return s

        # Strategy 0: Direct NSE Fetch via jugaad-data (Bulletproof for Indian Equities)
        if sym.endswith('.NS'):
            try:
                base_sym = sym.replace('.NS', '')
                from jugaad_data.nse import stock_df
                from datetime import date, timedelta
                
                days = 365
                if period == '2y': days = 730
                if period == '5y': days = 1825
                
                to_date = date.today()
                from_date = to_date - timedelta(days=days)
                
                def _fetch_jugaad():
                    return stock_df(symbol=base_sym, from_date=from_date, to_date=to_date, series="EQ")
                    
                df = await asyncio.to_thread(_fetch_jugaad)
                if df is not None and not df.empty:
                    df = df.rename(columns={
                        "DATE": "date",
                        "OPEN": "open",
                        "HIGH": "high",
                        "LOW": "low",
                        "CLOSE": "close",
                        "VOLUME": "volume"
                    })
                    df['date'] = pd.to_datetime(df['date'])
                    df = df.set_index('date')
                    df = df.sort_index()
                    df = df[['open', 'high', 'low', 'close', 'volume']]
                    logger.info(f"✅ Strategy 0 Success: {sym} via jugaad-data ({len(df)} candles)")
                    return df
            except Exception as e:
                logger.warning(f"⚠️ Strategy 0 Failed for {sym} via jugaad-data: {e}")

        # Strategy 1: Try with proxy + rotated UA (2 attempts)
        from app.services.proxy_manager import proxy_manager
        for attempt in range(2):
            proxy = await proxy_manager.get_proxy()
            if proxy:  # Only use proxy if one actually exists — never pass None
                ua = random.choice(USER_AGENTS)
                session = _make_session(ua)
                try:
                    def _fetch_proxy():
                        return yf.Ticker(sym, session=session, proxy=proxy).history(period=period, interval=interval)
                    df = await asyncio.to_thread(_fetch_proxy)
                    if df is not None and not df.empty:
                        df.columns = [c.lower() for c in df.columns]
                        return df
                except Exception:
                    pass
                await asyncio.sleep(random.uniform(0.3, 0.8))

        # Strategy 2: Direct fetch with rotated UA only (no proxy — guaranteed to attempt)
        for attempt in range(2):
            ua = random.choice(USER_AGENTS)
            session = _make_session(ua)
            try:
                def _fetch_direct():
                    return yf.Ticker(sym, session=session).history(period=period, interval=interval)
                df = await asyncio.to_thread(_fetch_direct)
                if df is not None and not df.empty:
                    df.columns = [c.lower() for c in df.columns]
                    return df
            except Exception:
                pass
            await asyncio.sleep(random.uniform(0.2, 0.5))

        # Strategy 3: Bare yfinance call — no session, no proxy (last resort)
        try:
            def _fetch_bare():
                return yf.Ticker(sym).history(period=period, interval=interval)
            df = await asyncio.to_thread(_fetch_bare)
            if df is not None and not df.empty:
                df.columns = [c.lower() for c in df.columns]
                return df
        except Exception:
            pass

        return pd.DataFrame()


    async def analyze_stock(self, sym: str, job_id: str = None):
        """
        Executes a Multi-Strategy Swing Scan (Pullback & Breakout).
        """
        try:
            if job_id and self.job_states.get(job_id, {}).get("stop_requested"): return None

            # 1. Fetch 1D Data - Swap to Anti-Ban Evasion
            # Minimum 60 candles (SMA 50 + buffer). SMA 200 is optional and handled gracefully.
            df_1d = await self._fetch_swing_ohlc_with_evasion(sym, period="1y", interval="1d")
            if df_1d is None or df_1d.empty or len(df_1d) < 60:
                print(f"  ⛔ {sym}: DATA INSUFFICIENT ({len(df_1d) if df_1d is not None and not df_1d.empty else 0} candles < 60 min)", flush=True)
                return None
            
            candle_count = len(df_1d)
            
            # --- Phase 5: Anti-Staleness Timestamp Check ---
            from datetime import datetime, timedelta
            try:
                latest_date = pd.to_datetime(df_1d.index[-1])
                if latest_date.tzinfo is not None:
                     latest_date = latest_date.tz_convert(None)
                if datetime.utcnow() - latest_date > timedelta(hours=96):
                    print(f"  ⛔ {sym}: STALE DATA (Last candle: {latest_date.strftime('%Y-%m-%d')})", flush=True)
                    return None
            except Exception as e:
                pass
                
            real_price = safe_scalar(df_1d['close'].iloc[-1])
            if real_price <= 0: return None
            
            # 2. Parallel Strategy Execution
            nifty_20d_ret = self.market_context.get("nifty_20d_return", 0)
            
            ctx = ta_swing.compute_context(df_1d)
            
            pb_result = await asyncio.to_thread(ta_swing.analyze_pullback, df_1d, nifty_20d_ret, ctx)
            bo_result = await asyncio.to_thread(ta_swing.analyze_breakout, df_1d, nifty_20d_ret, ctx)

            # --- Diagnostic Log: Strategy Results ---
            pb_status = "✅ MATCH" if pb_result.get("match") else f"❌ {pb_result.get('reason', 'No Match')}"
            bo_status = "✅ MATCH" if bo_result.get("match") else f"❌ {bo_result.get('reason', 'No Match')}"
            print(f"  📊 {sym} | ₹{real_price} | {candle_count}D | PB: {pb_status} | BO: {bo_status}", flush=True)

            # --- Phase 3: Sector Dominance Filtering ---
            sector = market_service.get_sector_for_symbol(sym)
            sector_perf = self.market_context.get("sector_performance", {})
            sector_return = sector_perf.get(sector, 0.0)
            
            # Apply conditional Sector Strength filtering for breakouts
            if bo_result.get("match"):
                if sector_return < 0.0:
                    bo_result["match"] = False
                    bo_result["reason"] = f"Sector Weakness ({round(sector_return, 2)}%) invalidates Breakout"
                    print(f"    🔻 {sym}: Breakout KILLED by Sector Weakness ({sector}: {round(sector_return, 2)}%)", flush=True)
                elif self.market_context.get("ad_ratio", 1.0) < 0.6:
                    bo_result["match"] = False
                    bo_result["reason"] = f"Heavy Market Selling Pressure (A/D < 0.6) invalidates Breakout"
                    print(f"    🔻 {sym}: Breakout KILLED by A/D Ratio < 0.6", flush=True)

            if pb_result.get("match") and self.market_context.get("ad_ratio", 1.0) < 0.5:
                pb_result["match"] = False
                pb_result["reason"] = f"Heavy Market Selling Pressure (A/D < 0.5) invalidates Pullback"
                print(f"    🔻 {sym}: Pullback KILLED by A/D Ratio < 0.5", flush=True)

            # 3. Conflict Resolution & Selection
            selected = None
            is_nifty_bullish = self.market_context.get("nifty_bullish", False)
            is_market_exhausted = self.market_context.get("nifty_exhausted", False)
            
            if is_market_exhausted:
                if pb_result["match"]:
                    selected = pb_result
                    selected["market_context"] = "OVERBOUGHT_RECOVERY"
                else:
                    print(f"    ⏭️ {sym}: SKIP (Market Exhausted, no Pullback)", flush=True)
                    return None
            
            high_20 = safe_scalar(df_1d['high'].iloc[-21:-1].max())
            is_near_high = (high_20 - real_price) / max(high_20, 1) < 0.01

            if pb_result["match"] and bo_result["match"]:
                if is_nifty_bullish or is_near_high:
                    selected = bo_result
                else:
                    selected = pb_result
            elif bo_result["match"]:
                if is_nifty_bullish or is_near_high:
                    selected = bo_result
            elif pb_result["match"]:
                selected = pb_result
                
            if not selected: 
                return None

            strategy_name = selected.get("strategy", "UNKNOWN")

            # Extract Stop Loss and Target from the selected strategy
            sl = selected.get("stop_loss", 0.0)
            target = selected.get("target", 0.0)

            # ====================================================================
            # 4. V3 CONVICTION-WEIGHTED SCORING MATRIX (100-Point Scale)
            # ====================================================================
            conviction = selected.get("conviction", 0)
            if conviction < 5:
                # Minimum viable product check: skip low quality setups entirely
                return None
                
            # Components:
            #   Conviction (from ta_swing)   : 0-25 pts
            #   Volume Quality               : 0-15 pts
            #   Relative Strength            : 0-10 pts
            #   Market Context Alignment     : 0-15 pts (-10 penalty possible)
            #   ADX Trend Strength           : 0-10 pts
            #   Strategy-Specific Bonus      : 0-15 pts
            #   MACD/OBV Institutional       : 0-10 pts
            # ====================================================================
            score = 0
            score_breakdown = []
            
            # --- Component 1: Conviction Score (max 25) ---
            # This is pre-calculated by ta_swing based on pattern quality + indicator confluence
            conviction = selected.get("conviction", 0)
            max_conviction = 12 if selected["strategy"] == "BREAKOUT" else 10
            conv_score = round((conviction / max(max_conviction, 1)) * 25)
            score += conv_score
            score_breakdown.append(f"Conviction: +{conv_score} ({conviction}/{max_conviction})")
            
            # --- Component 2: Volume Quality (max 15) ---
            vol_ratio = selected.get("vol_ratio", 1.0)
            if vol_ratio > 2.5:
                vol_score = 15
            elif vol_ratio > 2.0:
                vol_score = 12
            elif vol_ratio > 1.5:
                vol_score = 8
            elif vol_ratio > 1.2:
                vol_score = 5
            else:
                vol_score = 0
            score += vol_score
            score_breakdown.append(f"Vol: +{vol_score} ({round(vol_ratio, 1)}x)")
            
            # --- Component 3: Relative Strength vs Nifty (max 10) ---
            stock_ret = selected.get("stock_20d_return", 0)
            nifty_ret = self.market_context.get("nifty_20d_return", 0)
            rs_spread = stock_ret - nifty_ret
            if rs_spread > 10:
                rs_score = 10
            elif rs_spread > 5:
                rs_score = 7
            elif rs_spread > 2:
                rs_score = 4
            else:
                rs_score = 1
            score += rs_score
            score_breakdown.append(f"RS: +{rs_score} (+{round(rs_spread, 1)}%)")
            
            # --- Component 4: Market Context Alignment (max 15, can penalize) ---
            mkt_score = 0
            nifty_rsi = self.market_context.get("nifty_rsi", 50)
            ad_ratio = self.market_context.get("ad_ratio", 1.0)
            
            # Nifty trend alignment
            if is_nifty_bullish:
                mkt_score += 5
            
            # Breadth support
            if ad_ratio >= 1.2:
                mkt_score += 5
            elif ad_ratio >= 0.8:
                mkt_score += 2
            
            # Sector tailwind
            if sector_return > 2.0:
                mkt_score += 5
            elif sector_return > 0:
                mkt_score += 2
                
            # Penalty: Exhausted market for breakouts
            if is_market_exhausted and selected["strategy"] == "BREAKOUT":
                mkt_score -= 10
                score_breakdown.append("Exhaustion Penalty: -10")
            
            score += max(-10, mkt_score)
            score_breakdown.append(f"Mkt: +{max(-10, mkt_score)}")
            
            # --- Component 5: ADX Trend Strength (max 10) ---
            adx_val = selected.get("adx", 0)
            if adx_val >= 35:
                adx_score = 10
            elif adx_val >= 30:
                adx_score = 7
            elif adx_val >= 25:
                adx_score = 4
            else:
                adx_score = 0
            score += adx_score
            score_breakdown.append(f"ADX: +{adx_score} ({round(adx_val, 1)})")
            
            # --- Component 6: Strategy-Specific Bonuses (max 15) ---
            strat_bonus = 0
            if selected["strategy"] == "PULLBACK":
                # SMA50 bounce is higher quality than EMA20
                zone_val = next((r["value"] for r in selected.get("reasons", []) if r["label"] == "ZONE"), "")
                if "SMA 50" in zone_val:
                    strat_bonus += 10
                    score_breakdown.append("SMA50 Bounce: +10")
                else:
                    strat_bonus += 5
                # Reversal pullback (RSI < 40) is higher conviction
                if selected.get("setup_type") == "REVERSAL_PULLBACK":
                    strat_bonus += 5
                    score_breakdown.append("Reversal: +5")
            elif selected["strategy"] == "BREAKOUT":
                # Near 20D high
                if is_near_high:
                    strat_bonus += 5
                    score_breakdown.append("NearHigh: +5")
                # Squeeze breakout (Bollinger)
                if selected.get("is_squeeze_breakout"):
                    strat_bonus += 10
                    score_breakdown.append("Squeeze: +10")
                else:
                    strat_bonus += 3
            score += min(15, strat_bonus)
            
            # --- Component 7: MACD/OBV Institutional Signals (max 10) ---
            inst_score = 0
            if selected.get("macd_bullish"):
                inst_score += 3
            if selected.get("macd_expanding") or selected.get("macd_recovering"):
                inst_score += 3
            if selected.get("obv_rising"):
                inst_score += 4
            score += inst_score
            score_breakdown.append(f"Inst: +{inst_score}")
            
            # --- Final Score Normalization ---
            final_score = round(min(100, max(0, score)), 1)
            
            # Confidence Level (tighter thresholds for V3)
            confidence = "LOW"
            if final_score >= 80: confidence = "HIGH"
            elif final_score >= 60: confidence = "MEDIUM"

            # --- HIGH VISIBILITY MATCH LOG ---
            icon = "🚀 BREAKOUT" if strategy_name == "BREAKOUT" else "📥 PULLBACK"
            print(f"  ✅ {icon} ━━ {sym} ━━ Score: {final_score} ({confidence}) | {' | '.join(score_breakdown)}", flush=True)
            print(f"     Entry: ₹{real_price} | SL: ₹{sl} | Target: ₹{target} | Risk/Share: ₹{round(abs(real_price - sl), 2)}", flush=True)

            # 5. Metadata & Advisory
            try:
                def _get_info():
                    import yfinance as yf
                    return yf.Ticker(sym).info or {}
                company_data = await asyncio.to_thread(_get_info)
            except Exception:
                company_data = {}
            name = company_data.get("shortName", sym)
            # Sector already fetched above

            from app.services.advisor_engine import advisor_engine
            advisory = advisor_engine.generate_advice(
                sym, real_price, company_data, {}, {}, {}, None, mode="swing"
            )

            # 6. Portfolio & Risk Management Integration
            if job_id and self.job_states.get(job_id, {}).get("stop_requested"): return None
            port_result = portfolio_engine.calculate_position_size(real_price, sl)
            
            # Update verdict with specific portfolio advice
            verdict = f"SWING ({selected['strategy']}): {selected['setup_type']} detected. "
            if selected.get("strategy") == "BREAKOUT":
                verdict += f"Hybrid Exit: Partial at {target} (1.5R), then trail via EMA 9. "
            else:
                verdict += f"Conservative Target at {target} (2R). "
            
            verdict += f"Ref Capital (1L) Allocation: {port_result['exposure_pct']}%."

            return {
                "symbol": sym,
                "name": name,
                "sector": sector,
                "price": round(real_price, 2),
                "score": final_score,
                "confidence": confidence,
                "strategy": selected["strategy"],
                "setup_type": selected["setup_type"],
                "signal": "BUY",
                "verdict": verdict,
                "strategic_summary": advisory.get('entry_analysis', {}).get('rationale', 'Confirmed structure.'),
                "entry": round(real_price, 2),
                "stop_loss": sl,
                "target": target,
                "is_hybrid": selected.get("is_hybrid_exit", False),
                "hold_duration": "2 to 21 Days",
                "priority": final_score,
                "reasons": selected.get("reasons", []),
                # --- Position Sizing & Portfolio Metadata ---
                "risk_per_trade_pct": portfolio_engine.risk_per_trade_pct, 
                "position_size_type": "PORTFOLIO_CONSERVATIVE",
                "ref_capital": portfolio_engine.total_capital, 
                "risk_per_share": round(abs(real_price - sl), 2),
                "suggested_quantity": port_result["quantity"],
                "capital_required": port_result["capital_required"],
                "portfolio_exposure": port_result["exposure_pct"]
            }

        except Exception as e:
            logger.error(f"❌ Swing Analyzer Error for {sym}: {e}")
            return None

    async def run_scan(self, job_id: str, logger=None):
        self.start_job(job_id)
        
        # 0. Pre-Scan Risk Circuit Breakers
        # We check both the daily loss limit (2%) and the total portfolio risk limit (5%)
        # before starting a single scan.
        total_cap = portfolio_engine.total_capital
        
        if await trade_manager.check_daily_loss(total_cap) == "STOP_TRADING":
            self.update_job_progress(job_id, 100, 100, "⚠️ SCAN ABORTED: Daily Loss Limit Breached (2% Cap).")
            return {"status": "ABORTED", "reason": "DAILY_LOSS_LIMIT"}

        if await trade_manager.is_risk_limit_reached(total_cap):
            self.update_job_progress(job_id, 100, 100, "⚠️ SCAN ABORTED: Portfolio Risk Limit Reached (5% Cap).")
            return {"status": "ABORTED", "reason": "RISK_LIMIT_REACHED"}

        await self.refresh_market_context()
        
        try:
            state = self.job_states[job_id]
            self.update_job_progress(job_id, 5, 100, "Discovery: Syncing market universe...")

            full_list = await market_discovery.get_full_market_list()
            symbols = [s['symbol'] for s in full_list]
            
            if not symbols:
                 self.update_job_progress(job_id, 100, 100, "Scan Complete (Empty)")
                 return state

            exclusion_list = ['ADANIGREEN.NS', 'ADANIPOWER.NS']
            symbols = [s for s in symbols if s not in exclusion_list]
            random.shuffle(symbols)

            total_stocks = len(symbols)
            state = self.job_states.get(job_id)
            if not state:
                logger.error(f"Job state not found for {job_id}")
                return {"status": "error"}
            
            # [V12.2] Link main task for immediate cancellation
            state["main_task"] = asyncio.current_task()
            state["total_steps"] = total_stocks
                
            sync_task = asyncio.create_task(self._progress_loop(job_id, total_stocks))

            concurrency_limit = 15 # Increased for faster scanning
            semaphore = asyncio.Semaphore(concurrency_limit)

            async def sem_task(sym, idx):
                if state.get("stop_requested"): return

                # [V12.1 PAUSE CHECK] ⏸️
                while job_id in self.job_states and state.get("pause_requested"):
                    if state.get("stop_requested"): return
                    await asyncio.sleep(1)
                
                # [V12.2] Immediate Stop Guard
                if state.get("stop_requested"): return

                async with semaphore:
                    # [V12.2] Re-check after acquiring slot
                    if state.get("stop_requested"): return
                    current_active = state.get("active_symbols", [])
                    if len(current_active) >= 5: current_active.pop(0)
                    current_active.append(sym)
                    
                    # Log to database for UI
                    self.update_job_progress(job_id, idx, total_stocks, f"Analyzing: {sym} ({idx}/{total_stocks})", current_active)
                    
                    # Log to stdout for Debugging/Terminal Visibility
                    if idx % 50 == 0:
                        print(f"📡 [SCANNER] Progress: {idx}/{total_stocks} stocks analyzed...", flush=True)
                    
                    res = await self.analyze_stock(sym, job_id)
                    if res: self.add_job_result(job_id, res)
                    else: self.add_failed_symbol(job_id, {"symbol": sym})

            tasks = [sem_task(sym, i) for i, sym in enumerate(symbols)]
            await asyncio.gather(*tasks)
            
            # 5. Finalization — Swing signals already have full position sizing embedded.
            # portfolio_engine.select_trades/build_trade_plan are calibrated for Longterm format
            # and silently return empty on Swing data. Use raw scan_results directly.
            scan_results = state.get("results", [])
            print(f"✅ [SWING SCAN COMPLETE] {len(scan_results)} qualified signals found from {total_stocks} scanned.", flush=True)
            
            # Sort by score descending and cap at top 50
            trade_plan = sorted(scan_results, key=lambda x: x.get("score", 0), reverse=True)[:50]

        except asyncio.CancelledError:
            pass
        except Exception as e:
            import traceback
            logger.error(f"Global Scan Error: {e}")
            traceback.print_exc()
            trade_plan = []
            scan_results = []
        finally:
            if job_id in self.job_states: 
                self.job_states[job_id]["stop_requested"] = True
                self.job_states[job_id]["is_running"] = False
            if 'sync_task' in locals(): await sync_task

        # Return the finalized Trade Plan
        final_payload = {
            "total_scanned": total_stocks,
            "raw_signal_count": len(scan_results),
            "trade_plan_count": len(trade_plan),
            "data": trade_plan,
            "status_msg": f"Swing Scan Complete: {len(trade_plan)} high-conviction trades identified from {total_stocks} stocks."
        }
        
        if job_id in self.job_states: del self.job_states[job_id]
        return sanitize_data(final_payload)

    async def manage_active_trades(self):
        """
        Daily Lifecycle Maintenance: Update active trades with latest market data.
        - Calculates Trailing Stops
        - Checks Time Stops
        - Triggers SL/TP Exits
        """
        active_trades = trade_manager.get_active_trades()
        if not active_trades:
            return

        logger.info(f"🛰️ Trade Manager: Updating {len(active_trades)} active positions...")
        all_symbols = [t["symbol"] for t in active_trades]
        
        market_stats = {}
        for sym in all_symbols:
            try:
                # Fetch 1D OHLC including technicals needed for trailing
                df = await market_service.get_ohlc(sym, period="1mo", interval="1d")
                if df is None or df.empty: continue
                
                # Fetch EMA 9/20 for Trailing Stops
                from ta.trend import EMAIndicator
                ema_9 = EMAIndicator(close=df['close'], window=9).ema_indicator().iloc[-1]
                ema_20 = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
                
                market_stats[sym] = {
                    "close": safe_scalar(df['close'].iloc[-1]),
                    "high": safe_scalar(df['high'].iloc[-1]),
                    "low": safe_scalar(df['low'].iloc[-1]),
                    "ema_9": safe_scalar(ema_9),
                    "ema_20": safe_scalar(ema_20)
                }
            except Exception as e:
                logger.error(f"Failed to fetch update data for {sym}: {e}")

        # Execute updates in bulk
        await trade_manager.update_trades(market_stats)
        logger.info("✅ Trade Manager: Portfolio maintenance complete.")

    async def execute_trade_suggestion(self, trade_data: Dict[str, Any]):
        """
        Manually 'Enters' a trade suggestion into the Portfolio/TradeManager.
        This transition from a 'Signal' to an 'Active Position'.
        """
        symbol = trade_data.get("symbol")
        if not symbol:
            return {"status": "ERROR", "message": "Invalid trade data."}
            
        # 1. Final Risk Check
        if await trade_manager.is_risk_limit_reached(portfolio_engine.total_capital):
            logger.warning(f"🚫 Cannot execute {symbol}: Portfolio risk limit reached.")
            return {"status": "BLOCKED", "message": "Risk limit reached."}
            
        # 2. Add to TradeManager (Lifecycle tracking starts)
        await trade_manager.add_trade(trade_data)
        
        # 3. Add to Portfolio (Capital/Sector tracking starts)
        portfolio_engine.update_active_positions(trade_data)
        
        return {"status": "SUCCESS", "message": f"Monitoring started for {symbol}."}

    async def _progress_loop(self, job_id: str, total: int):
        from sqlalchemy.orm.attributes import flag_modified
        from app.db.session import AsyncSessionLocal
        from app.models.job import Job
        from sqlalchemy import select
        
        while job_id in self.job_states and self.job_states[job_id].get("is_running"):
            try:
                state = self.job_states.get(job_id)
                if not state: break
                async with AsyncSessionLocal() as session:
                    stmt = select(Job).where(Job.id == job_id)
                    res = await session.execute(stmt)
                    job_obj = res.scalars().first()
                    if job_obj:
                        if job_obj.status == "stopped":
                            state["stop_requested"] = True
                            state["is_running"] = False
                            # [V12.2] Explicitly cancel the main execution task
                            main_task = state.get("main_task")
                            if main_task and not main_task.done():
                                main_task.cancel()
                            break
                        
                        # [V12.1 EXTERNAL PAUSE CHECK] ⏸️
                        if job_obj.status == "paused":
                            state["pause_requested"] = True
                        elif state.get("pause_requested") and job_obj.status == "processing":
                            state["pause_requested"] = False
                        
                        current_result = job_obj.result or {}
                        current_result.update({
                            "progress": state.get("progress", 0),
                            "total_steps": total,
                            "active_symbols": list(state.get("active_symbols", [])),
                            "status_msg": state.get("status_msg", ""),
                            "data": list(state.get("results", []))[-50:] # Keep last 50 matches live
                        })
                        job_obj.result = sanitize_data(current_result)
                        flag_modified(job_obj, "result")
                        await session.commit()
            except Exception as e:
                logger.error(f"⚠️ [SWING PROGRESS] DB write error: {e}")
            await asyncio.sleep(3.0)

    async def stop_job(self, job_id: str):
        if job_id in self.job_states:
            self.job_states[job_id]["stop_requested"] = True
            self.job_states[job_id]["is_running"] = False
            print(f"🛑 [SWING] Stop Signal Received for {job_id}")

    async def pause_job(self, job_id: str):
        if job_id in self.job_states:
            self.job_states[job_id]["pause_requested"] = True
            print(f"⏸️ [SWING] Pause Signal Received for {job_id}")

    async def resume_job(self, job_id: str):
        if job_id in self.job_states:
            self.job_states[job_id]["pause_requested"] = False
            print(f"▶️ [SWING] Resume Signal Received for {job_id}")

swing_engine = SwingEngine()
