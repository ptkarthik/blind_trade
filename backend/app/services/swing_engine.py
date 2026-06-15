import asyncio
import time
import random
from typing import Dict, Any, List
import pandas as pd
import logging
import warnings
from datetime import datetime

# Suppress harmless numpy timezone warnings from jugaad_data
warnings.filterwarnings("ignore", message="no explicit representation of timezones available for np.datetime64")

from app.services.market_data import market_service
from app.services.market_discovery import market_discovery
from app.services.ta_swing import ta_swing, safe_scalar
from app.services.portfolio_engine import portfolio_engine
from app.services.trade_manager import trade_manager
from app.services.earnings_service import earnings_service
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
            # V3 Kite-Native: Use Kite index OHLC directly — no more NIFTYBEES Yahoo workaround
            from app.services.kite_data import kite_data
            df_nifty = None
            if kite_data.is_ready:
                try:
                    df_nifty = await kite_data.get_index_ohlc("NIFTY 50", period="1y", interval="1d")
                    if df_nifty is not None and not df_nifty.empty:
                        print(f" [KITE MARKET CONTEXT] Fetched NIFTY 50 index directly ({len(df_nifty)} candles)", flush=True)
                except Exception as e:
                    logger.warning(f"️ Kite index fetch failed, falling back to Yahoo: {e}")
                    df_nifty = None
            
            # Fallback: Yahoo NIFTYBEES
            if df_nifty is None or df_nifty.empty:
                df_nifty = await self._fetch_swing_ohlc_with_evasion("NIFTYBEES.NS", period="1y", interval="1d")
                if df_nifty is not None and not df_nifty.empty:
                    print(f"[YAHOO FALLBACK] Fetched NIFTYBEES for market context ({len(df_nifty)} candles)", flush=True)
            
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
                logger.info(f" Market Context: NIFTY {'Bullish' if self.market_context['nifty_bullish'] else 'Bearish'} (RSI: {round(nifty_rsi, 1)})")
        except Exception as e:
            logger.error(f"Failed to refresh market context: {e}")

        try:
            sector_perf = await market_service.get_sector_performances()
            self.market_context["sector_performance"] = sector_perf
            logger.info("️ Sector Heatmap Refreshed.")
        except Exception as e:
            self.market_context["sector_performance"] = {}
            logger.error(f"Failed to fetch sector performance: {e}")

        try:
            ad_ratio = await market_service.get_advance_decline_ratio()
            self.market_context["ad_ratio"] = ad_ratio
            logger.info(f"️ Market Breadth (A/D Ratio): {round(ad_ratio, 2)}")
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

        # Strategy -1: Kite Connect (Primary)
        from app.services.kite_data import kite_data
        if kite_data.is_ready and sym.endswith('.NS'):
            try:
                df = await kite_data.fetch_ohlc(sym, period=period, interval=interval)
                if df is not None and not df.empty:
                    logger.info(f" Strategy Kite Success: {sym} ({len(df)} candles)")
                    print(f" [KITE SWING DATA] Successfully fetched {len(df)} historical candles for {sym}", flush=True)
                    return df
            except Exception as e:
                logger.warning(f"️ Strategy Kite Failed for {sym}: {e}")
                print(f"️ [KITE SWING DATA] Failed for {sym}: {e}", flush=True)

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
                    logger.info(f" Strategy 0 Success: {sym} via jugaad-data ({len(df)} candles)")
                    return df
            except Exception as e:
                logger.warning(f"️ Strategy 0 Failed for {sym} via jugaad-data: {e}")

        # Strategy 1: Try with proxy + rotated UA (2 attempts)
        from app.services.proxy_manager import proxy_manager
        for attempt in range(2):
            proxy = await proxy_manager.get_proxy()
            if proxy:  # Only use proxy if one actually exists — never pass None
                ua = random.choice(USER_AGENTS)
                try:
                    def _fetch_proxy():
                        return yf.Ticker(sym).history(period=period, interval=interval)
                    df = await asyncio.to_thread(_fetch_proxy)
                    if df is not None and not df.empty:
                        df.columns = [c.lower() for c in df.columns]
                        return df
                except Exception:
                    pass
                await asyncio.sleep(random.uniform(0.3, 0.8))

        # Strategy 2: Direct fetch with rotated UA only (no proxy — guaranteed to attempt)
        for attempt in range(2):
            try:
                def _fetch_direct():
                    return yf.Ticker(sym).history(period=period, interval=interval)
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
                print(f"   {sym}: DATA INSUFFICIENT ({len(df_1d) if df_1d is not None and not df_1d.empty else 0} candles < 60 min)", flush=True)
                return None
            
            candle_count = len(df_1d)
            
            # --- Phase 5: Anti-Staleness Timestamp Check ---
            from datetime import datetime, timedelta
            try:
                latest_date = pd.to_datetime(df_1d.index[-1])
                if latest_date.tzinfo is not None:
                     latest_date = latest_date.tz_convert(None)
                if datetime.utcnow() - latest_date > timedelta(hours=96):
                    print(f"   {sym}: STALE DATA (Last candle: {latest_date.strftime('%Y-%m-%d')})", flush=True)
                    return None
            except Exception as e:
                pass
                
            real_price = safe_scalar(df_1d['close'].iloc[-1])
            if real_price <= 0: return None
            
            # 2. Parallel Strategy Execution
            nifty_20d_ret = self.market_context.get("nifty_20d_return", 0)
            
            ctx = ta_swing.compute_context(df_1d)
            
            # V1.1 Swing Hardening: Query offline cache to prevent binary gap traps
            earnings_risk = earnings_service.is_in_earnings_window(sym)
            
            pb_result = await asyncio.to_thread(ta_swing.analyze_pullback, df_1d, nifty_20d_ret, ctx, earnings_risk)
            bo_result = await asyncio.to_thread(ta_swing.analyze_breakout, df_1d, nifty_20d_ret, ctx, earnings_risk)

            # --- Diagnostic Log: Strategy Results ---
            pb_status = " MATCH" if pb_result.get("match") else f" {pb_result.get('reason', 'No Match')}"
            bo_status = " MATCH" if bo_result.get("match") else f" {bo_result.get('reason', 'No Match')}"
            print(f"   {sym} | ₹{real_price} | {candle_count}D | PB: {pb_status} | BO: {bo_status}", flush=True)

            # --- [V44] Sector Dominance — converted from hard kills to score penalties ---
            # These now feed into the scoring matrix instead of zeroing out matches
            sector = market_service.get_sector_for_symbol(sym)
            sector_perf = self.market_context.get("sector_performance", {})
            sector_data = sector_perf.get(sector, 0.0)
            if isinstance(sector_data, dict):
                sector_return = sector_data.get("1d", 0.0)
                sector_return_5d = sector_data.get("5d", 0.0)
            else:
                sector_return = sector_data
                sector_return_5d = sector_data
                
            ad_penalty = 0
            sector_penalty = 0
            
            if bo_result.get("match"):
                # [V45] Tiered sector penalty (was flat -15 for any negative — too harsh)
                if sector_return < -2.0:
                    sector_penalty = 15
                    print(f"    ️ {sym}: Breakout sector penalty −15 ({sector}: {round(sector_return, 2)}%)", flush=True)
                elif sector_return < -1.0:
                    sector_penalty = 8
                    print(f"    ️ {sym}: Breakout sector penalty −8 ({sector}: {round(sector_return, 2)}%)", flush=True)
                elif sector_return < 0.0:
                    sector_penalty = 3
                    print(f"    ️ {sym}: Breakout sector penalty −3 ({sector}: {round(sector_return, 2)}%)", flush=True)
                if self.market_context.get("ad_ratio", 1.0) < 0.6:
                    ad_penalty = 10
                    print(f"    ️ {sym}: Breakout A/D penalty −10 (A/D < 0.6)", flush=True)

            if pb_result.get("match") and self.market_context.get("ad_ratio", 1.0) < 0.35:
                ad_penalty = max(ad_penalty, 10)
                print(f"    ️ {sym}: Pullback A/D penalty −10 (A/D < 0.35)", flush=True)

            # 3. Conflict Resolution & Selection
            selected = None
            is_nifty_bullish = self.market_context.get("nifty_bullish", False)
            is_market_exhausted = self.market_context.get("nifty_exhausted", False)
            
            if is_market_exhausted:
                if pb_result["match"]:
                    selected = pb_result
                    selected["market_context"] = "OVERBOUGHT_RECOVERY"
                else:
                    print(f"    ️ {sym}: SKIP (Market Exhausted, no Pullback)", flush=True)
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
            if conviction < 3:
                # Minimum viable product check: skip low quality setups entirely
                print(f"    ️ {sym}: Conviction too low ({conviction}/12) — skipping", flush=True)
                return None
                
            # Components:
            #   Conviction (from ta_swing)   : 0-25 pts
            #   Volume Quality               : 0-15 pts
            #   Volume Persistence [V45.2]   : 0-5  pts (independent of quality)
            #   Relative Strength            : 0-10 pts
            #   Momentum Acceleration [V45.2]: 0-5  pts
            #   Market Context Alignment     : 0-15 pts (-10 penalty possible)
            #   ADX Trend Strength           : 0-10 pts
            #   Strategy-Specific Bonus      : 0-15 pts
            #   Consolidation Duration [V45.2]: 0-7 pts (breakout only)
            #   MACD/OBV Institutional       : 0-10 pts
            #   NSE Delivery % [V45.2]       : -5 to +8 pts
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
            selected.setdefault("reasons", []).append({"text": f"Core Conviction Score ({conviction}/{max_conviction})", "impact": conv_score, "layer": 1, "type": "positive"})
            
            # --- Component 2: Volume Quality (max 15) ---
            vol_ratio = selected.get("vol_ratio", 1.0)
            # [V45] Granular volume tiers (confirmation-weighted, not dominating)
            if vol_ratio > 4.0:
                vol_score = 15
            elif vol_ratio > 3.0:
                vol_score = 13
            elif vol_ratio > 2.5:
                vol_score = 11
            elif vol_ratio > 2.0:
                vol_score = 9
            elif vol_ratio > 1.5:
                vol_score = 6
            elif vol_ratio > 1.2:
                vol_score = 3
            else:
                vol_score = 0
            score += vol_score
            score_breakdown.append(f"Vol: +{vol_score} ({round(vol_ratio, 1)}x)")
            if vol_score > 0: selected.setdefault("reasons", []).append({"text": f"Volume Quality ({round(vol_ratio, 1)}x)", "impact": vol_score, "layer": 2, "type": "positive"})
            
            # --- Component 2.5: Volume Persistence Bonus (max 5) [V45.2] ---
            # Institutional accumulation persists for 3-5 sessions. One-day spikes can be noise.
            # [V45.2 FIX] INDEPENDENT scoring — persistence gets its own 5pt budget.
            # Old cap at 15 combined killed persistence for stocks with high single-day volume.
            # Example: INFOBEAN at 11.3x daily + 5d avg 3.0x got ZERO persistence. Fixed.
            vol_3d = selected.get("vol_3d_avg", 1.0)
            vol_5d = selected.get("vol_5d_avg", 1.0)
            vol_persist_score = 0
            if vol_5d > 2.0:
                vol_persist_score = 5   # 5-day sustained heavy accumulation
            elif vol_5d > 1.5:
                vol_persist_score = 3   # 5-day moderate accumulation
            elif vol_3d > 1.5:
                vol_persist_score = 2   # 3-day short accumulation
            score += vol_persist_score
            if vol_persist_score > 0:
                score_breakdown.append(f"VolPersist: +{vol_persist_score} (3d:{round(vol_3d, 1)}x, 5d:{round(vol_5d, 1)}x)")
                selected.setdefault("reasons", []).append({"text": f"Sustained Volume ({round(vol_5d, 1)}x avg over 5d)", "impact": vol_persist_score, "layer": 2, "type": "positive"})
            
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
            selected.setdefault("reasons", []).append({"text": f"Relative Strength vs Nifty (+{round(rs_spread, 1)}%)", "impact": rs_score, "layer": 2, "type": "positive"})
            
            # --- Component 3.5: Momentum Acceleration Bonus (max 5) [V45.2] ---
            # RS Spread is backward-looking (20 days). A stock with low RS but strong
            # short-term momentum is STARTING to move — often the best entry point.
            # Example: INFOBEAN had RS +0.8% (20d) but +3.45% today with 11.3x volume.
            # This bonus detects that acceleration.
            accel_bonus = 0
            try:
                if len(df_1d) >= 6:
                    price_5d_ago = safe_scalar(df_1d['close'].iloc[-6])
                    if price_5d_ago > 0:
                        roc_5d = ((real_price - price_5d_ago) / price_5d_ago) * 100
                        # Low 20d RS but strong 5d move with volume persistence = acceleration
                        if rs_spread < 5 and roc_5d > 5 and vol_5d > 1.5:
                            accel_bonus = 5
                        elif rs_spread < 5 and roc_5d > 3 and vol_5d > 1.5:
                            accel_bonus = 3
                        if accel_bonus > 0:
                            score += accel_bonus
                            score_breakdown.append(f"Accel: +{accel_bonus} (5d ROC:{round(roc_5d, 1)}%, RS:{round(rs_spread, 1)}%, Vol5d:{round(vol_5d, 1)}x)")
                            selected.setdefault("reasons", []).append({"text": f"Momentum Acceleration (5d: +{round(roc_5d, 1)}% with sustained volume)", "impact": accel_bonus, "layer": 2, "type": "positive"})
            except Exception:
                pass
            
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
            
            # Sector tailwind [V2 Sector Momentum]
            if sector_return_5d > 5.0:
                mkt_score += 10
            elif sector_return_5d > 2.0 or sector_return > 2.0:
                mkt_score += 5
            elif sector_return_5d > 0 or sector_return > 0:
                mkt_score += 2
                
            # [V45] Dynamic exhaustion penalty based on Nifty RSI severity
            if selected["strategy"] == "BREAKOUT":
                if nifty_rsi > 85:
                    exhaust_pen = 8
                elif nifty_rsi > 80:
                    exhaust_pen = 5
                elif nifty_rsi > 75:
                    exhaust_pen = 3
                else:
                    exhaust_pen = 0
                if exhaust_pen > 0:
                    mkt_score -= exhaust_pen
                    score_breakdown.append(f"Exhaustion Penalty: -{exhaust_pen} (Nifty RSI: {round(nifty_rsi, 1)})")
                    selected.setdefault("reasons", []).append({"text": f"Market Exhaustion Risk (Nifty RSI: {round(nifty_rsi, 1)})", "impact": -exhaust_pen, "layer": 3, "type": "negative"})
            
            score += max(-10, mkt_score)
            score_breakdown.append(f"Mkt: +{max(-10, mkt_score)}")
            if mkt_score > 0: selected.setdefault("reasons", []).append({"text": "Market Context Alignment", "impact": mkt_score, "layer": 2, "type": "positive"})
            
            # --- Component 5: ADX Trend Strength (max 10) [V2: Exhaustion Tiers] ---
            # Wilder's ADX theory: ADX > 40 signals trend exhaustion, not continuation.
            # ADX > 50 = extremely overbought trend, high mean-reversion probability.
            adx_val = selected.get("adx", 0)
            adx_penalty = 0
            if adx_val >= 50:
                adx_score = 0
                adx_penalty = 5  # Exhaustion penalty
                score_breakdown.append(f"ADX Exhaustion: -5 ({round(adx_val, 1)} > 50)")
                selected.setdefault("reasons", []).append({"text": f"ADX Exhaustion ({round(adx_val, 1)} > 50 = trend overheated)", "impact": -5, "layer": 3, "type": "negative"})
            elif adx_val >= 40:
                adx_score = 5  # Reduced from 10 — late-stage trend
            elif adx_val >= 35:
                adx_score = 10  # Healthy strong trend
            elif adx_val >= 30:
                adx_score = 7
            elif adx_val >= 25:
                adx_score = 4
            else:
                adx_score = 0
            score += adx_score - adx_penalty
            score_breakdown.append(f"ADX: +{adx_score} ({round(adx_val, 1)})")
            if adx_score > 0: selected.setdefault("reasons", []).append({"text": f"ADX Trend Strength ({round(adx_val, 1)})", "impact": adx_score, "layer": 1, "type": "positive"})
            
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
                
                # [V46] Day-1 Asymmetry Boost: Fresh breakouts close to EMA20 have
                # optimal risk/reward. They haven't run up yet, so they have room to grow.
                # Cartrade-type setups: breaking out but <5% above 20 EMA = low-risk entry.
                # This boosts safe, early breakouts above overextended ones in the ranking.
                asym_bonus = 0
                try:
                    if len(df_1d) >= 21:
                        from ta.trend import EMAIndicator
                        ema_20_val = safe_scalar(EMAIndicator(close=df_1d['close'], window=20).ema_indicator().iloc[-1])
                        if ema_20_val > 0:
                            ema20_dist = ((real_price - ema_20_val) / ema_20_val) * 100
                            if 0 < ema20_dist <= 5:
                                asym_bonus = 8
                                score_breakdown.append(f"V46 Fresh BO: +{asym_bonus} ({round(ema20_dist, 1)}% above EMA20)")
                                selected.setdefault("reasons", []).append({"text": f"Day-1 Fresh Breakout (only {round(ema20_dist, 1)}% above EMA20 — optimal entry)", "impact": asym_bonus, "layer": 2, "type": "positive"})
                                print(f"     V46 FRESH BREAKOUT BOOST: {sym} only {round(ema20_dist, 1)}% above EMA20 — bonus +{asym_bonus}", flush=True)
                            elif 0 < ema20_dist <= 8:
                                asym_bonus = 4
                                score_breakdown.append(f"V46 Ext BO: +{asym_bonus} ({round(ema20_dist, 1)}% above EMA20)")
                                selected.setdefault("reasons", []).append({"text": f"Breakout Momentum ({round(ema20_dist, 1)}% above EMA20 — buy the dip)", "impact": asym_bonus, "layer": 2, "type": "positive"})
                except Exception as e:
                    logger.debug(f"V46 Asymmetry boost check failed for {sym}: {e}")
                score += asym_bonus

            score += min(15, strat_bonus)
            if strat_bonus > 0: selected.setdefault("reasons", []).append({"text": "Strategy Specific Bonuses", "impact": min(15, strat_bonus), "layer": 1, "type": "positive"})
            
            # --- Component 6.3: Consolidation Duration Bonus (max 7, breakout only) [V45.2] ---
            # Longer consolidation before breakout = stronger move. 
            # 30+ days of tight range = massive energy stored. 10 days = weak base.
            consol_days = selected.get("consol_days", 0)
            consol_bonus = 0
            if selected["strategy"] == "BREAKOUT" and consol_days > 0:
                if consol_days >= 30:
                    consol_bonus = 7   # Month+ base — institutional accumulation
                elif consol_days >= 20:
                    consol_bonus = 5   # Strong base
                elif consol_days >= 15:
                    consol_bonus = 3   # Decent base
                elif consol_days >= 10:
                    consol_bonus = 1   # Minimal base
                if consol_bonus > 0:
                    score += consol_bonus
                    score_breakdown.append(f"Base: +{consol_bonus} ({consol_days}d consolidation)")
                    selected.setdefault("reasons", []).append({"text": f"Consolidation Base ({consol_days} days — longer base = stronger breakout)", "impact": consol_bonus, "layer": 1, "type": "positive"})
            
            # --- Component 6.5: Post-Earnings Momentum Boost [V2] ---
            pe_score = 0
            try:
                days_since_earnings = earnings_service.get_days_since_earnings(sym)
                if 0 <= days_since_earnings <= 5:
                    if len(df_1d) >= (days_since_earnings + 2):
                        price_pre_earnings = safe_scalar(df_1d['close'].iloc[-(days_since_earnings + 2)])
                        if price_pre_earnings > 0:
                            post_earnings_return = ((real_price - price_pre_earnings) / price_pre_earnings) * 100
                            if post_earnings_return > 5.0:
                                pe_score = 10
                                score += pe_score
                                score_breakdown.append(f"Earn Boost: +10 (+{round(post_earnings_return, 1)}% post-ER)")
                                selected.setdefault("reasons", []).append({"text": f"Post-Earnings Momentum Boost (+{round(post_earnings_return, 1)}% since earnings {days_since_earnings} days ago)", "impact": pe_score, "layer": 2, "type": "positive"})
            except Exception as e:
                logger.debug(f"Post-earnings check failed for {sym}: {e}")
            
            # --- Component 6.8: Momentum Igniter (Early Parabolic Catch) ---
            # Catching stocks exactly as they explode, before they hit extension penalties.
            # Purely additive. Does not regress existing logic.
            igniter_bonus = 0
            if selected["strategy"] == "BREAKOUT" and vol_ratio >= 4.0:
                try:
                    if len(df_1d) >= 60:
                        daily_roc = ((real_price - safe_scalar(df_1d['close'].iloc[-2])) / max(safe_scalar(df_1d['close'].iloc[-2]), 0.01)) * 100
                        if daily_roc >= 5.0:
                            local_low_60d = safe_scalar(df_1d['low'].iloc[-60:].min())
                            if local_low_60d > 0:
                                local_extension = real_price / local_low_60d
                                if local_extension <= 1.25: # < 25% above 60d low (Catching on Day 1)
                                    from ta.trend import EMAIndicator
                                    local_ema_10 = safe_scalar(EMAIndicator(close=df_1d['close'], window=10).ema_indicator().iloc[-1])
                                    if local_ema_10 > 0:
                                        local_ema10_dist = ((real_price - local_ema_10) / local_ema_10) * 100
                                        if local_ema10_dist <= 10.0: # Not overextended from short-term mean
                                            igniter_bonus = 15
                                            score += igniter_bonus
                                            selected["setup_type"] = "MOMENTUM_IGNITER"
                                            score_breakdown.append(f"Igniter Bonus: +{igniter_bonus} (Day 1 Parabolic)")
                                            selected.setdefault("reasons", []).append({"text": f"🔥 Momentum Igniter (Day 1 Parabolic explosion caught early)", "impact": igniter_bonus, "layer": 1, "type": "positive"})
                                            print(f"     🔥 MOMENTUM IGNITER DETECTED: {sym} — bonus +{igniter_bonus}", flush=True)
                except Exception as e:
                    logger.debug(f"Momentum Igniter check failed for {sym}: {e}")
            
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
            if inst_score > 0: selected.setdefault("reasons", []).append({"text": "Institutional Flow (MACD/OBV)", "impact": inst_score, "layer": 2, "type": "positive"})
            
            # --- Component 7.5: NSE Delivery % (max 8, can penalize -5) [V45.2] ---
            # Delivery % is the single best signal of institutional commitment.
            # >60% = institutions TAKING DELIVERY (not day-trading) → +8
            # >45% = moderate institutional interest → +4
            # <25% with high volume = NOISE volume (intraday speculation) → -5
            delivery_score = 0
            try:
                from app.services.delivery_service import delivery_service
                delivery_pct = await delivery_service.get_delivery_pct(sym)
                if delivery_pct is not None:
                    selected["delivery_pct"] = delivery_pct
                    if delivery_pct >= 60:
                        delivery_score = 8
                        score_breakdown.append(f"Delivery: +8 ({delivery_pct}% institutional)")
                        selected.setdefault("reasons", []).append({"text": f"High Delivery ({delivery_pct}% — institutions taking delivery)", "impact": 8, "layer": 2, "type": "positive"})
                    elif delivery_pct >= 45:
                        delivery_score = 4
                        score_breakdown.append(f"Delivery: +4 ({delivery_pct}%)")
                        selected.setdefault("reasons", []).append({"text": f"Moderate Delivery ({delivery_pct}%)", "impact": 4, "layer": 2, "type": "positive"})
                    elif delivery_pct >= 30:
                        delivery_score = 1
                        score_breakdown.append(f"Delivery: +1 ({delivery_pct}%)")
                        selected.setdefault("reasons", []).append({"text": f"Moderate Delivery ({delivery_pct}%)", "impact": 1, "layer": 2, "type": "positive"})
                    elif delivery_pct < 25 and vol_ratio > 3.0:
                        # High volume but very low delivery = noise, not accumulation
                        delivery_score = -5
                        score_breakdown.append(f"Delivery: -5 (NOISE — {delivery_pct}% delivery on {round(vol_ratio, 1)}x volume)")
                        selected.setdefault("reasons", []).append({"text": f"Noise Volume Alert ({delivery_pct}% delivery on {round(vol_ratio, 1)}x volume — mostly intraday speculation)", "impact": -5, "layer": 3, "type": "negative"})
                        print(f"     NOISE VOLUME: {sym} delivery only {delivery_pct}% on {round(vol_ratio, 1)}x volume", flush=True)
                    score += delivery_score
                else:
                    score_breakdown.append("Delivery: N/A")
            except Exception as e:
                logger.debug(f"Delivery fetch failed for {sym}: {e}")
            
            # ====================================================================
            # V2 SCORING PENALTIES — Anti-Trap Filters (from backtest forensics)
            # ====================================================================
            v2_penalty = 0
            
            # --- V2 Penalty 1: Parabolic Extension Detection ---
            # If stock is >50% above its 60-day low, it's over-extended.
            # KSHINTL was +120% → would have scored -25 here.
            try:
                if len(df_1d) >= 60:
                    low_60d = safe_scalar(df_1d['low'].iloc[-60:].min())
                else:
                    low_60d = safe_scalar(df_1d['low'].min())
                if low_60d > 0:
                    extension_ratio = real_price / low_60d
                    if extension_ratio > 2.0:
                        ext_pen = 25
                        v2_penalty += ext_pen
                        score_breakdown.append(f"V2 Parabolic: -{ext_pen} ({round((extension_ratio-1)*100)}% above 60d low)")
                        selected.setdefault("reasons", []).append({"text": f"️ Parabolic Extension ({round((extension_ratio-1)*100)}% above 60d low — extreme mean-reversion risk)", "impact": -ext_pen, "layer": 3, "type": "negative"})
                        print(f"     V2 PARABOLIC TRAP: {sym} is {round((extension_ratio-1)*100)}% above 60d low — penalty -{ext_pen}", flush=True)
                    elif extension_ratio > 1.5:
                        ext_pen = 15
                        v2_penalty += ext_pen
                        score_breakdown.append(f"V2 Extended: -{ext_pen} ({round((extension_ratio-1)*100)}% above 60d low)")
                        selected.setdefault("reasons", []).append({"text": f"️ Over-Extended ({round((extension_ratio-1)*100)}% above 60d low)", "impact": -ext_pen, "layer": 3, "type": "negative"})
                        print(f"     V2 EXTENDED: {sym} is {round((extension_ratio-1)*100)}% above 60d low — penalty -{ext_pen}", flush=True)
            except Exception as e:
                logger.debug(f"V2 Extension check failed for {sym}: {e}")
            
            # --- V2 Penalty 2: Short-Term Chasing Detection ---
            # If 5-day ROC > 15%, the stock has moved too fast too recently.
            # KSHINTL had +20% in 2 days → would have scored -10 here.
            # [V46] Climax Volume Trap: High volume after huge run = exhaustion, NOT accumulation.
            # Old logic waived the penalty for vol_5d >= 2.0x. This caused AHCL-type traps where
            # a stock runs +15% on 4x volume, gets max score, then dumps -4.5% the next day.
            # New logic: If ROC is extreme AND today's volume is a spike (>4x), it's climax volume.
            try:
                if len(df_1d) >= 6:
                    price_5d_ago = safe_scalar(df_1d['close'].iloc[-6])
                    if price_5d_ago > 0:
                        roc_5d = ((real_price - price_5d_ago) / price_5d_ago) * 100
                        # [V45] Strategy-specific thresholds: breakouts need more momentum room
                        chase_threshold = 20 if strategy_name == "BREAKOUT" else 15
                        if roc_5d > chase_threshold:
                            # [V46 CLIMAX TRAP] High single-day volume spike on overextended stock = exhaustion
                            # vol_ratio > 4x on a stock already up >15% = everyone who wanted to buy has bought
                            if vol_ratio > 4.0 and roc_5d > 15:
                                climax_pen = 15
                                v2_penalty += climax_pen
                                score_breakdown.append(f"V46 Climax Trap: -{climax_pen} (5d ROC: +{round(roc_5d, 1)}% with {round(vol_ratio, 1)}x volume spike)")
                                selected.setdefault("reasons", []).append({"text": f"Climax Volume Trap ({round(vol_ratio, 1)}x volume spike after +{round(roc_5d, 1)}% run — exhaustion risk)", "impact": -climax_pen, "layer": 3, "type": "negative"})
                                print(f"     V46 CLIMAX TRAP: {sym} 5d ROC = +{round(roc_5d, 1)}% with {round(vol_ratio, 1)}x vol spike — penalty -{climax_pen}", flush=True)
                            # [V45.2] Sustained multi-day volume with moderate extension = genuine accumulation
                            elif vol_5d >= 2.0 and roc_5d <= 25:
                                score_breakdown.append(f"V2 Chasing: WAIVED (5d ROC: +{round(roc_5d, 1)}% but vol 5d avg {round(vol_5d, 1)}x = accumulation)")
                                print(f"     V2 CHASING WAIVED: {sym} 5d ROC = +{round(roc_5d, 1)}% but vol persistence {round(vol_5d, 1)}x confirms accumulation", flush=True)
                            else:
                                chase_pen = 10
                                v2_penalty += chase_pen
                                score_breakdown.append(f"V2 Chasing: -{chase_pen} (5d ROC: +{round(roc_5d, 1)}% > {chase_threshold}%)")
                                selected.setdefault("reasons", []).append({"text": f"Chasing Alert (5-day ROC: +{round(roc_5d, 1)}% > {chase_threshold}% threshold)", "impact": -chase_pen, "layer": 3, "type": "negative"})
                                print(f"     V2 CHASING: {sym} 5d ROC = +{round(roc_5d, 1)}% > {chase_threshold}% — penalty -{chase_pen}", flush=True)
            except Exception as e:
                logger.debug(f"V2 Chasing check failed for {sym}: {e}")
            
            # --- V2 Penalty 3: Volume Distribution Detection ---
            # High volume at >30% above 60d low = institutional distribution, not accumulation.
            try:
                # [V45] Distribution only on RED candles — green + high volume = accumulation
                latest_candle_red = safe_scalar(df_1d['close'].iloc[-1]) < safe_scalar(df_1d['open'].iloc[-1])
                if low_60d > 0 and extension_ratio > 1.3 and vol_ratio > 3.0 and latest_candle_red:
                    dist_pen = 5
                    v2_penalty += dist_pen
                    score_breakdown.append(f"V2 Distribution: -{dist_pen} ({round(vol_ratio, 1)}x vol at {round((extension_ratio-1)*100)}% extended, RED candle)")
                    selected.setdefault("reasons", []).append({"text": f"️ Distribution Volume ({round(vol_ratio, 1)}x on RED candle while {round((extension_ratio-1)*100)}% extended)", "impact": -dist_pen, "layer": 3, "type": "negative"})
                    print(f"     V2 DISTRIBUTION: {sym} {round(vol_ratio, 1)}x volume at {round((extension_ratio-1)*100)}% extended (RED) — penalty -{dist_pen}", flush=True)
            except Exception as e:
                logger.debug(f"V2 Distribution check failed for {sym}: {e}")
            
            # --- V46 Penalty 4: Short-Term EMA Overextension ---
            # If price is >10% above its 10-day EMA, it is statistically likely to mean-revert.
            # This catches AHCL-type traps that pass the 60-day extension check (50% threshold)
            # but are severely stretched above their short-term moving average.
            try:
                if len(df_1d) >= 11:
                    from ta.trend import EMAIndicator
                    ema_10 = safe_scalar(EMAIndicator(close=df_1d['close'], window=10).ema_indicator().iloc[-1])
                    if ema_10 > 0:
                        ema10_dist = ((real_price - ema_10) / ema_10) * 100
                        if ema10_dist > 15:
                            ema_ext_pen = 15
                            v2_penalty += ema_ext_pen
                            score_breakdown.append(f"V46 EMA10 Stretch: -{ema_ext_pen} ({round(ema10_dist, 1)}% above EMA10)")
                            selected.setdefault("reasons", []).append({"text": f"EMA10 Overextended ({round(ema10_dist, 1)}% above — extreme mean-reversion risk)", "impact": -ema_ext_pen, "layer": 3, "type": "negative"})
                            print(f"     V46 EMA10 STRETCH: {sym} is {round(ema10_dist, 1)}% above EMA10 — penalty -{ema_ext_pen}", flush=True)
                        elif ema10_dist > 10:
                            ema_ext_pen = 10
                            v2_penalty += ema_ext_pen
                            score_breakdown.append(f"V46 EMA10 Extended: -{ema_ext_pen} ({round(ema10_dist, 1)}% above EMA10)")
                            selected.setdefault("reasons", []).append({"text": f"EMA10 Extended ({round(ema10_dist, 1)}% above — elevated mean-reversion risk)", "impact": -ema_ext_pen, "layer": 3, "type": "negative"})
                            print(f"     V46 EMA10 EXTENDED: {sym} is {round(ema10_dist, 1)}% above EMA10 — penalty -{ema_ext_pen}", flush=True)
            except Exception as e:
                logger.debug(f"V46 EMA10 Extension check failed for {sym}: {e}")
            
            # --- V46 Penalty 5: Trap Memory Check ---
            # Compares this stock's indicators against all known trap patterns
            # learned from past TRAP-classified stocks. The more traps we find,
            # the smarter this check becomes.
            try:
                from app.services.trap_memory import trap_memory
                trap_indicators = {
                    "roc_5d": locals().get("roc_5d", 0),
                    "vol_ratio": vol_ratio,
                    "ema10_dist": locals().get("ema10_dist", 0),
                    "delivery_pct": selected.get("delivery_pct", 50),
                    "adx": selected.get("adx", 0),
                }
                trap_penalty, trap_reason = await trap_memory.check_stock(trap_indicators)
                if trap_penalty > 0:
                    v2_penalty += trap_penalty
                    score_breakdown.append(f"V46 Trap Memory: -{trap_penalty}")
                    selected.setdefault("reasons", []).append({"text": trap_reason, "impact": -trap_penalty, "layer": 3, "type": "negative"})
                    print(f"     V46 TRAP MEMORY: {sym} matches known trap — penalty -{trap_penalty}", flush=True)
            except Exception as e:
                logger.debug(f"V46 Trap Memory check failed for {sym}: {e}")

            # ====================================================================
            # V4 Institutional Upgrades (Component 8: Math Extensions)
            # ====================================================================
            inst_math_score = 0
            
            # --- W-MACD Confluence ---
            w_macd_bullish = selected.get("w_macd_bullish", False)
            if w_macd_bullish:
                inst_math_score += 5
                score_breakdown.append("W-MACD: +5")
                selected.setdefault("reasons", []).append({"text": "Weekly MACD Bullish Confluence", "impact": 5, "layer": 2, "type": "positive"})
            
            # --- Anchored VWAP (AVWAP) ---
            avwap = selected.get("avwap_60d_low", 0.0)
            if avwap > 0:
                # If price is bouncing off AVWAP (within 3% above it)
                avwap_dist = (real_price - avwap) / avwap
                if 0 <= avwap_dist <= 0.03:
                    inst_math_score += 5
                    score_breakdown.append(f"AVWAP Bounce: +5 ({round(avwap_dist*100,1)}%)")
                    selected.setdefault("reasons", []).append({"text": f"AVWAP Support Bounce (60d low anchor)", "impact": 5, "layer": 2, "type": "positive"})
                elif avwap_dist < 0:
                    # Below AVWAP is a structural breakdown, penalty
                    inst_math_score -= 5
                    score_breakdown.append(f"Below AVWAP: -5")
                    selected.setdefault("reasons", []).append({"text": f"Below AVWAP (Warning)", "impact": -5, "layer": 3, "type": "negative"})
            
            # --- Volume Profile (VPVR POC) ---
            poc = selected.get("vpvr_poc_90d", 0.0)
            if poc > 0:
                poc_dist = (real_price - poc) / poc
                if 0 <= poc_dist <= 0.03:
                    inst_math_score += 5
                    score_breakdown.append(f"POC Bounce: +5")
                    selected.setdefault("reasons", []).append({"text": f"VPVR POC Bounce (High volume node)", "impact": 5, "layer": 2, "type": "positive"})
                    
            score += inst_math_score

            # --- Archetype Detection: Hidden Alpha Support Bounce ---
            is_hidden_alpha_divergence = False
            if selected.get("strategy") == "PULLBACK":
                # Strong volume accumulation
                if vol_ratio >= 1.4 and vol_5d >= 1.4:
                    # Diverging relative strength
                    if rs_spread >= 3.0:
                        # Sector is dragging it down
                        if sector_penalty > 0 or ad_penalty > 0:
                            is_hidden_alpha_divergence = True

            if is_hidden_alpha_divergence:
                # Refund the macro penalties because the micro-signals override them
                rebate = ad_penalty + sector_penalty
                score += rebate
                score_breakdown.append(f"HiddenAlpha Rebate: +{rebate}")
                selected.setdefault("reasons", []).append({
                    "text": "Hidden Alpha Divergence (Institutional Volume + RS overriding Sector Weakness)", 
                    "impact": rebate, 
                    "layer": 2, 
                    "type": "positive"
                })
                # Zero out the penalties so they don't drag down the final calculation
                ad_penalty = 0
                sector_penalty = 0

            # --- Final Score Normalization ---
            # [V44] Apply A/D and sector penalties from soft filters
            # [V2] Apply new anti-trap penalties
            total_penalty = ad_penalty + sector_penalty + v2_penalty
            score -= total_penalty
            final_score = round(min(100, max(0, score)), 1)
            if ad_penalty > 0 or sector_penalty > 0:
                score_breakdown.append(f"Mkt Penalty: -{ad_penalty + sector_penalty}")
                selected.setdefault("reasons", []).append({"text": "Breadth/Sector Penalty", "impact": -(ad_penalty + sector_penalty), "layer": 3, "type": "negative"})
            
            # Confidence Level (tighter thresholds for V3)
            confidence = "LOW"
            if final_score >= 80: confidence = "HIGH"
            elif final_score >= 60: confidence = "MEDIUM"

            # [V43] Conviction-based signal classification
            if final_score >= 75:
                signal_type = "BUY_STRONG"
            elif final_score >= 50:
                signal_type = "BUY"
            else:
                signal_type = "HOLD"  # Low-conviction: surface but don't recommend action

            # --- HIGH VISIBILITY MATCH LOG ---
            icon = " BREAKOUT" if strategy_name == "BREAKOUT" else " PULLBACK"
            print(f"   {icon} ━━ {sym} ━━ Score: {final_score} ({confidence}) [{signal_type}] | {' | '.join(score_breakdown)}", flush=True)
            print(f"     Entry: ₹{real_price} | SL: ₹{sl} | Target: ₹{target} | Risk/Share: ₹{round(abs(real_price - sl), 2)}", flush=True)

            # 5. Metadata & Advisory
            # [V43] Use market_service for name instead of slow yfinance .info call
            name = market_service.get_name_for_symbol(sym) or sym.replace('.NS', '').replace('.BO', '')

            from app.services.advisor_engine import advisor_engine
            advisory = advisor_engine.generate_advice(
                sym, real_price, {}, selected, {}, {}, None, mode="swing"
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

            # --- AMO EXECUTOR & PRE-MARKET PRECONDITIONS ---
            atr_val = safe_scalar(ctx['atr'].iloc[-1])
            ema20_val = safe_scalar(ctx['ema_20'].iloc[-1])
            obv_s_val = ctx['obv']
            obv_rising_val = False
            if len(obv_s_val) >= 10:
                obv_rising_val = safe_scalar(obv_s_val.iloc[-1]) > safe_scalar(obv_s_val.iloc[-10])

            c_h_val = safe_scalar(df_1d['high'].iloc[-1])
            c_l_val = safe_scalar(df_1d['low'].iloc[-1])
            c_range_val = c_h_val - c_l_val
            upper_wick_val = c_h_val - max(safe_scalar(df_1d['open'].iloc[-1]), real_price)
            upper_wick_pct = (upper_wick_val / c_range_val) * 100 if c_range_val > 0 else 0

            ema20_dist_val = ((real_price - ema20_val) / ema20_val) * 100 if ema20_val > 0 else 0
            
            amo_action = "✅ PLACE AMO LIMIT"
            amo_reason = "Momentum confirmed at EOD."
            if ema20_dist_val > 5.0:
                amo_action = "❌ DO NOT AMO"
                amo_reason = f"Overextended {round(ema20_dist_val, 1)}% above EMA20. Wait for morning dip."
            elif upper_wick_pct > 40:
                amo_action = "❌ DO NOT AMO"
                amo_reason = f"Heavy selling pressure late in day (Upper wick {round(upper_wick_pct)}%)."
            elif not obv_rising_val and vol_ratio < 1.5:
                amo_action = "❌ DO NOT AMO"
                amo_reason = "Weak institutional flow. Requires live confirmation tomorrow."

            premarket_checks = []
            if amo_action == "✅ PLACE AMO LIMIT":
                exhaustion_level = real_price + (atr_val * 0.5)
                support_level = c_l_val
                premarket_checks.append(f"Cancel AMO if pre-market opens > ₹{round(exhaustion_level, 2)} (Exhaustion Risk)")
                premarket_checks.append(f"Cancel AMO if pre-market opens < ₹{round(support_level, 2)} (Support Failure)")

            # --- DYNAMIC HOLD DURATION ---
            dynamic_hold = "2 to 3 Weeks"
            if selected.get("setup_type") == "MOMENTUM_IGNITER":
                dynamic_hold = "1 to 3 Days"
            elif selected.get("strategy") == "PULLBACK":
                dynamic_hold = "5 to 10 Days"
            elif selected.get("strategy") == "BREAKOUT" and locals().get("consol_days", 0) >= 10:
                dynamic_hold = "3 to 6 Weeks"

            return {
                "symbol": sym,
                "name": name,
                "sector": sector,
                "price": round(real_price, 2),
                "score": final_score,
                "confidence": confidence,
                "strategy": selected["strategy"],
                "setup_type": selected["setup_type"],
                "signal": signal_type,
                "verdict": verdict,
                "strategic_summary": advisory.get('entry_analysis', {}).get('rationale', 'Confirmed structure.'),
                "entry": round(real_price, 2),
                "stop_loss": sl,
                "target": target,
                "is_hybrid": selected.get("is_hybrid_exit", False),
                "hold_duration": dynamic_hold,
                "priority": final_score,
                "delivery_pct": selected.get("delivery_pct"),
                "reasons": selected.get("reasons", []),
                "amo_action": amo_action,
                "amo_reason": amo_reason,
                "premarket_checks": premarket_checks,
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
            logger.error(f" Swing Analyzer Error for {sym}: {e}")
            return None

    async def run_scan(self, job_id: str, logger=None):
        scan_results = []
        trade_plan = []
        total_stocks = 0
        self.start_job(job_id)
        
        # 0. Pre-Scan Risk Circuit Breakers
        # We check both the daily loss limit (2%) and the total portfolio risk limit (5%)
        # before starting a single scan.
        total_cap = portfolio_engine.total_capital
        
        if await trade_manager.check_daily_loss(total_cap) == "STOP_TRADING":
            self.update_job_progress(job_id, 100, 100, "️ SCAN ABORTED: Daily Loss Limit Breached (2% Cap).")
            return {"status": "ABORTED", "reason": "DAILY_LOSS_LIMIT"}

        if await trade_manager.is_risk_limit_reached(total_cap):
            self.update_job_progress(job_id, 100, 100, "️ SCAN ABORTED: Portfolio Risk Limit Reached (5% Cap).")
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
                return {"status": "error", "data": []}
            
            # [V12.2] Link main task for immediate cancellation
            state["main_task"] = asyncio.current_task()
            state["total_steps"] = total_stocks
            sync_task = asyncio.create_task(self._progress_loop(job_id, total_stocks))

            concurrency_limit = 15 # Increased for faster scanning
            semaphore = asyncio.Semaphore(concurrency_limit)

            async def sem_task(sym, idx):
                if state.get("stop_requested"): return

                # [V12.1 PAUSE CHECK] ️
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
                        print(f" [SCANNER] Progress: {idx}/{total_stocks} stocks analyzed...", flush=True)
                    
                    res = await self.analyze_stock(sym, job_id)
                    if res: self.add_job_result(job_id, res)
                    # [V43] Don't add normal strategy rejections to failed_symbols
                    # Only actual data/fetch failures should be tracked

            tasks = [sem_task(sym, i) for i, sym in enumerate(symbols)]
            await asyncio.gather(*tasks)
            
            # 5. Finalization — Swing signals already have full position sizing embedded.
            # portfolio_engine.select_trades/build_trade_plan are calibrated for Longterm format
            # and silently return empty on Swing data. Use raw scan_results directly.
            scan_results = state.get("results", [])
            print(f" [SWING SCAN COMPLETE] {len(scan_results)} qualified signals found from {total_stocks} scanned.", flush=True)
            
            # Sort by score descending (DO NOT cap at 50, so HOLD stocks aren't dropped)
            trade_plan = sorted(scan_results, key=lambda x: x.get("score", 0), reverse=True)

            # --- AI BRAIN: FINAL GATEKEEPER ---
            from app.services.ai_brain import ai_brain
            
            top_5 = trade_plan[:5]
            if top_5:
                print(f"[AI BRAIN] Running Final Gatekeeper on Top {len(top_5)} setups...", flush=True)
                ai_results = []
                self.update_job_progress(job_id, total_stocks, total_stocks, "AI Gatekeeper analyzing Top 5 setups concurrently...", [s['symbol'] for s in top_5])
                
                async def analyze_single_setup(setup):
                    # [Institutional Upgrade Phase 2]
                    # In a production environment with unlocked APIs, we would fetch:
                    # 1. Open Interest (OI) from Kite NFO tokens
                    # 2. Fundamentals (PE, EPS) from an institutional data provider
                    # For now, we pass placeholders that the AI can ignore if null.
                    
                    indicators = {
                        "setup_type": setup.get("setup_type"),
                        "verdict": setup.get("verdict"),
                        "engine_score": setup.get("score"),
                        "open_interest_trend": "Not Available (API Restricted)",
                        "pe_ratio": "Not Available (API Restricted)"
                    }
                    return await ai_brain.analyze_trade_setup(
                        setup["symbol"], setup["strategy"], setup["price"], indicators, setup.get("reasons", [])
                    )

                ai_tasks = [analyze_single_setup(setup) for setup in top_5]
                ai_results = await asyncio.gather(*ai_tasks)
                
                approved_setups = []
                for setup, ai_res in zip(top_5, ai_results):
                    setup["ai_confidence"] = ai_res.get("ai_confidence", 0)
                    setup["ai_reason"] = ai_res.get("ai_reason", "AI Engine Error")
                    setup["ai_approved"] = ai_res.get("approved", True)
                    
                    if not setup["ai_approved"]:
                        print(f"  [X] AI VETOED {setup['symbol']}: {setup['ai_reason']}")
                    else:
                        print(f"  [OK] AI APPROVED {setup['symbol']} (Confidence: {setup['ai_confidence']})")
                        approved_setups.append(setup)
                        
                # Replace trade_plan with only the approved setups from the top 5
                # and any setups that were beyond the top 5 (which weren't evaluated by AI)
                # Wait, usually we only want to trade the top 5 anyway. Let's just keep the approved ones
                # plus the rest of the plan if needed. Let's just filter the whole trade plan.
                trade_plan = approved_setups + trade_plan[5:]
                
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

        # --- PERFORMANCE TRACKER: Snapshot top picks for EOD auditing ---
        try:
            from app.services.performance_tracker import performance_tracker
            await performance_tracker.snapshot_scan_results(job_id, trade_plan)
        except Exception as e:
            logger.debug(f"[TRACKER] Snapshot failed (non-critical): {e}")

        # Return the finalized Trade Plan
        from app.services.delivery_service import delivery_service
        final_payload = {
            "total_scanned": total_stocks,
            "raw_signal_count": len(scan_results),
            "trade_plan_count": len(trade_plan),
            "data": trade_plan,
            "status_msg": f"Swing Scan Complete: {len(trade_plan)} high-conviction trades identified from {total_stocks} stocks.",
            "delivery_date": getattr(delivery_service, "last_used_date", "Unknown")
        }
        
        if job_id in self.job_states: del self.job_states[job_id]
        return sanitize_data(final_payload)

    async def evaluate_active_position(self, sym: str, strategy: str):
        """
        Continuously evaluates an active position to calculate its ongoing technical health score,
        decoupled from strict fresh entry criteria.
        """
        try:
            df_1d = await self._fetch_swing_ohlc_with_evasion(sym, period="1y", interval="1d")
            if df_1d is None or df_1d.empty or len(df_1d) < 60:
                return None
            
            ctx = ta_swing.compute_context(df_1d)
            real_price = safe_scalar(df_1d['close'].iloc[-1])
            if real_price <= 0: return None

            rsi = safe_scalar(ctx['rsi'].iloc[-1])
            adx = safe_scalar(ctx['adx'].iloc[-1])
            macd_line = safe_scalar(ctx['macd_line'].iloc[-1])
            macd_signal = safe_scalar(ctx['macd_signal'].iloc[-1])
            macd_bullish = macd_line > macd_signal
            ema20 = safe_scalar(ctx['ema_20'].iloc[-1])
            sma50 = safe_scalar(ctx['sma_50'].iloc[-1])
            
            # Base Score starts at 50
            score = 50
            
            # 1. Moving Average Support (Trend) - max 30 points
            if real_price > ema20:
                score += 30
            elif real_price > sma50:
                score += 10
            else:
                score -= 20 # Broken trend
                
            # 2. Momentum (RSI) - max 15 points
            if rsi > 60: score += 15
            elif rsi > 50: score += 5
            elif rsi < 40: score -= 10
            
            # 3. Trend Strength (ADX) - max 15 points
            if adx > 25 and real_price > ema20: score += 15
            elif adx > 20: score += 5
            
            # 4. MACD Confluence - max 10 points
            if macd_bullish: score += 10
            else: score -= 5
            
            # 5. Market Context - max 10 points
            is_nifty_bullish = self.market_context.get("nifty_bullish", False)
            if is_nifty_bullish: score += 10
            
            # Clamp between 0 and 100
            score = max(0, min(100, score))
            
            # Build strategic summary
            summary_parts = []
            if real_price > ema20:
                summary_parts.append("✅ Holding above EMA20")
            elif real_price > sma50:
                summary_parts.append("⚠️ Below EMA20, testing SMA50")
            else:
                summary_parts.append("🚨 Trend Broken (Below SMA50)")
                
            summary_parts.append(f"RSI: {round(rsi, 1)}")
            summary_parts.append(f"MACD: {'Bullish' if macd_bullish else 'Bearish'}")
            
            return {
                "score": score,
                "setup_type": strategy,
                "strategic_summary": " | ".join(summary_parts),
                "rsi": rsi,
                "adx": adx,
                "macd_bullish": macd_bullish,
                "price": real_price,
                "signal": "HOLD" if score >= 40 else "SELL"
            }
        except Exception as e:
            logger.error(f"Failed to evaluate active position {sym}: {e}")
            return None

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

        logger.info(f"️ Trade Manager: Updating {len(active_trades)} active positions...")
        all_symbols = [t["symbol"] for t in active_trades]
        
        market_stats = {}
        for sym in all_symbols:
            try:
                # Fetch 1D OHLC including technicals needed for trailing
                df = await market_service.get_ohlc(sym, period="1mo", interval="1d")
                if df is None or df.empty: continue
                
                # Fetch EMA 9/20 for Trailing Stops
                from ta.trend import EMAIndicator
                ema_9_series = EMAIndicator(close=df['close'], window=9).ema_indicator()
                ema_20_series = EMAIndicator(close=df['close'], window=20).ema_indicator()
                
                # V1.1 Swing Hardening: Anchor trailing stops to T-1 (yesterday) to prevent intraday wicks from killing trades
                ema_9_prev = ema_9_series.iloc[-2] if len(ema_9_series) >= 2 else ema_9_series.iloc[-1]
                ema_20_prev = ema_20_series.iloc[-2] if len(ema_20_series) >= 2 else ema_20_series.iloc[-1]
                
                market_stats[sym] = {
                    "close": safe_scalar(df['close'].iloc[-1]),
                    "high": safe_scalar(df['high'].iloc[-1]),
                    "low": safe_scalar(df['low'].iloc[-1]),
                    "ema_9": safe_scalar(ema_9_series.iloc[-1]),
                    "ema_20": safe_scalar(ema_20_series.iloc[-1]),
                    "ema_9_prev": safe_scalar(ema_9_prev),
                    "ema_20_prev": safe_scalar(ema_20_prev)
                }
            except Exception as e:
                logger.error(f"Failed to fetch update data for {sym}: {e}")

        # Execute updates in bulk
        await trade_manager.update_trades(market_stats)
        logger.info(" Trade Manager: Portfolio maintenance complete.")

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
            logger.warning(f" Cannot execute {symbol}: Portfolio risk limit reached.")
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
                        
                        # [V12.1 EXTERNAL PAUSE CHECK] ️
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
                logger.error(f"️ [SWING PROGRESS] DB write error: {e}")
            await asyncio.sleep(3.0)

    async def stop_job(self, job_id: str):
        if job_id in self.job_states:
            self.job_states[job_id]["stop_requested"] = True
            self.job_states[job_id]["is_running"] = False
            print(f" [SWING] Stop Signal Received for {job_id}")

    async def pause_job(self, job_id: str):
        if job_id in self.job_states:
            self.job_states[job_id]["pause_requested"] = True
            print(f"️ [SWING] Pause Signal Received for {job_id}")

    async def resume_job(self, job_id: str):
        if job_id in self.job_states:
            self.job_states[job_id]["pause_requested"] = False
            print(f"▶️ [SWING] Resume Signal Received for {job_id}")

swing_engine = SwingEngine()
