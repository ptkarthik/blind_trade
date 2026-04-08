import asyncio
import time
from app.services.market_data import market_service
from app.services.ta import ta_engine
# Removed Circular Import
from app.services.fundamentals import fundamental_engine
from app.services.risk_sentiment import risk_engine

# Global Cache with Strict Separation
GLOBAL_SECTOR_CACHE = {
    "intraday": {},
    "longterm": {}
}

class BackgroundRunner:
    def __init__(self):
        self.running = False
        # Global Semaphore to share rate limits across ALL modes
        # This allows us to run Intraday + Longterm in PARALLEL without doubling request rate
        self.sem = asyncio.Semaphore(2)
        
    async def start(self):
        # self.running = True
        print("🚀 Background Runner: Auto-Mode DISABLED (User Control Only)")
        # while self.running:
        #     try:
        #         # Update BOTH modes in PARALLEL
        #         # Shared semaphore ensures we don't exceed rate limits
        #         t1 = self.update_market_data("longterm") # User requested priority
        #         t2 = self.update_market_data("intraday")
        #         await asyncio.gather(t1, t2)
        #     except Exception as e:
        #         print(f"Background Loop Error: {e}")
            
        #     # Sleep 60s
        #     await asyncio.sleep(60)

    async def update_market_data(self, mode):
        """
        Iterates through all sectors for a specific MODE.
        Strict separation of logic.
        """
        print(f"🔄 Background: Starting {mode.upper()} Market Scan...")
        start_time = time.time()
        
        sectors = ["Banking", "Finance", "IT", "Auto", "Pharma", "Energy", "FMCG", "Metal", "Infrastructure", "Realty", "Services"]
        
        # Use Global Semaphore
        sem = self.sem
        
        # Mode Config
        timeframe = "15m" if mode == "intraday" else "1wk"
        period = "5d" if mode == "intraday" else "1y"

        async def process_sector(sector_name):
            symbols = market_service.get_stocks_by_sector(sector_name)
            if not symbols: return sector_name, []
            
            async def analyze_one(sym):
                async with sem:
                    try:
                        # Strict Delay to respect API limits
                        await asyncio.sleep(2.0)
                        
                        # 1. Fetch (Strict Separation)
                        df_task = market_service.get_ohlc(sym, period=period, interval=timeframe) 
                        price_task = market_service.get_live_price(sym)
                        
                        df, price_data = await asyncio.gather(df_task, price_task)
                        
                        real_price = price_data.get("price", 0.0)
                        market_cap = price_data.get("market_cap", 0.0)
                        
                        if df.empty and real_price == 0: return None
                        
                        # 2. Analyze (Strict Mode Passing) - Offloaded to Thread to prevent blocking Event Loop
                        analysis = await asyncio.to_thread(ta_engine.analyze_stock, df, mode=mode)
                        if not analysis: return None
                        
                        # --- LONG TERM ENGINE INTEGRATION (Mirroring signals.py) ---
                        final_score = analysis.get("score", 0)
                        reasons = analysis.get("reasons", [])
                        groups = analysis.get("groups", {})
                        
                        if mode == "longterm":
                             try:
                                # Fetch Extra Data
                                fund_task = market_service.get_fundamentals(sym)
                                ext_task = market_service.get_extended_data(sym)
                                fundamentals, extended = await asyncio.gather(fund_task, ext_task)
                                
                                # Run Engines (Offloaded)
                                fund_analysis = await asyncio.to_thread(fundamental_engine.analyze, fundamentals)
                                risk_analysis = await asyncio.to_thread(risk_engine.analyze, extended, fundamentals)
                                
                                # Combine Scores
                                tech_score = final_score
                                fund_score = fund_analysis["score"]
                                sent_score = risk_analysis["score"]
                                
                                # Weighted Average
                                final_score = (fund_score * 0.45) + (tech_score * 0.25) + (sent_score * 0.30)
                                final_score = round(final_score, 1)
                                
                                # Merge Reasons
                                reasons = []
                                reasons.extend(analysis.get("reasons", [])[:2])
                                reasons.extend(fund_analysis["details"])
                                reasons.extend(risk_analysis["details"])
                                
                                # Merge Groups for Modal
                                groups = {
                                    "Technical": {"score": tech_score, "details": analysis.get("reasons", [])},
                                    "Fundamental": {"score": fund_score, "details": fund_analysis["details"], "metrics": fund_analysis["raw_metrics"]},
                                    "Sentiment & Risk": {"score": sent_score, "details": risk_analysis["details"], "metrics": risk_analysis["components"]}
                                }
                             except Exception as e:
                                 print(f"Longterm analysis failed for {sym}: {e}")
                                 # Fallback to technical-only if fundamentals fail
                        
                        # 3. Format & Logic
                        score = final_score
                        current_price = real_price if real_price else analysis.get("close")
                        
                        cap_cat = "Small"
                        if market_cap > 200000000000: cap_cat = "Large"
                        elif market_cap > 50000000000: cap_cat = "Mid"
                        
                        # --- DYNAMIC TARGETS (RESTORED SIGNALS.PY LOGIC) ---
                        try:
                            # ATR Logic
                            df['range_pct'] = (df['high'] - df['low']) / df['close']
                            volatility = df['range_pct'].tail(14).mean()
                            volatility = max(min(volatility, 0.05), 0.008)
                        except:
                            volatility = 0.015

                        # Ratio Adjustment per Mode
                        if mode == "longterm":
                            # Long Term: Wider Stops, Bigger Targets
                            sl_dist = volatility * 3.0 
                            tp_dist = volatility * 6.0 # 1:2 on Weekly moves
                        else:
                            # Intraday: Tight Scalp
                            sl_dist = volatility * 1.5 
                            tp_dist = volatility * 2.5
                        
                        # Signal based on FINAL SCORE for Longterm, Trend for Intraday
                        if mode == "longterm":
                             # Relaxed Threshold to ensure population
                             # Score > 50 = Positive Outlook (BUY/ACCUMULATE)
                             # Score <= 50 = Negative Outlook (SELL/AVOID)
                             signal = "BUY" if final_score >= 50 else "SELL"
                        else:
                             signal = "BUY" if analysis.get("trend") == "BULLISH" else "SELL"
                        
                        if signal == "BUY":
                            stop_loss = round(current_price * (1 - sl_dist), 2)
                            target = round(current_price * (1 + tp_dist), 2)
                        elif signal == "SELL":
                            stop_loss = round(current_price * (1 + sl_dist), 2)
                            target = round(current_price * (1 - tp_dist), 2)
                        else:
                            stop_loss = 0
                            target = 0

                        return {
                            "symbol": sym,
                            "score": score,
                            "signal": signal,
                            "entry": current_price,
                            "stop_loss": stop_loss,
                            "target": target,
                            "reasons": reasons,
                            "groups": groups,
                            "market_cap_category": cap_cat,
                            "analysis_mode": mode.upper() # Explicit Mode
                        }
                    except Exception as e:
                        return None

            tasks = [analyze_one(s) for s in symbols]
            sector_res = await asyncio.gather(*tasks)
            valid = [r for r in sector_res if r]
            # Split
            buys = [r for r in valid if r["signal"] == "BUY"]
            sells = [r for r in valid if r["signal"] == "SELL"]
            
            buys.sort(key=lambda x: x["score"], reverse=True)
            sells.sort(key=lambda x: x["score"], reverse=False)
            
            # Return ALL results (Frontend handles filtering by Cap/Top 5)
            # This ensures Mid/Small caps are present in the dataset
            timestamp = time.strftime("%H:%M:%S")
            return sector_name, {"buys": buys, "sells": sells, "last_updated": timestamp}

        tasks = [process_sector(s) for s in sectors]
        results = await asyncio.gather(*tasks)
        
        # Store in Mode-Specific Cache
        for name, data in results:
            if data:
                GLOBAL_SECTOR_CACHE[mode][name] = data
                
        duration = time.time() - start_time
        print(f"✅ Background: {mode.upper()} Complete in {round(duration, 2)}s.")

runner = BackgroundRunner()
