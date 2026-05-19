from fastapi import APIRouter, Depends
from sqlalchemy import func, desc
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.job import Job
from app.services.market_data import market_service
from app.services.scanner_engine import longterm_scanner_engine
from app.services.intraday_engine import intraday_engine
from app.services.portfolio_engine import portfolio_engine
from app.services.utils import sanitize_data # Use shared version
import asyncio
import numpy as np
import uuid
from datetime import datetime, timedelta

def sanitize_json_data(data):
    """Helper for final API responses"""
    return sanitize_data(data)

def get_job_pulse_stats(job: Job):
    """Helper to calculate IST timings for the dashboard"""
    stats = {
        "started_at": "",
        "finished_at": "",
        "duration": "",
        "status": job.status if job else "unknown"
    }
    if not job:
        return stats
        
    # UTC to IST (+5:30)
    if job.created_at:
        ist_start = job.created_at + timedelta(hours=5, minutes=30)
        stats["started_at"] = ist_start.strftime("%H:%M:%S")
        
    if job.updated_at:
        ist_end = job.updated_at + timedelta(hours=5, minutes=30)
        stats["finished_at"] = ist_end.strftime("%H:%M:%S")
        
        if job.status in ["completed", "stopped"]:
            diff = job.updated_at - job.created_at
            mins, secs = divmod(int(diff.total_seconds()), 60)
            stats["duration"] = f"{mins}m {secs}s"
        elif job.status == "processing":
            stats["duration"] = "Scanning..."
            
    return stats

router = APIRouter()

def sanitize_json_data(data):
    """
    Ensures data is JSON-serializable by cleaning NaNs and Infinity.
    Required for on-demand analysis results.
    """
    return sanitize_data(data)

@router.get("/today")
async def get_todays_signals(
    mode: str = "longterm", 
    job_id: str = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns structured Top 100 buys, sells, holds for the dashboard.
    """
    try:
        if mode == "longterm": job_type = "full_scan"
        elif mode == "swing": job_type = "swing_scan"
        else: job_type = "intraday"
        
        from datetime import datetime, timedelta
        since = datetime.utcnow() - timedelta(hours=24)
        
        # [V14.7 DIRECT LOCKING] Use specific Job ID if provided by the UI
        if job_id:
            valid_job = await db.get(Job, job_id)
        else:
            # [V30 FIX] ONLY show non-hidden jobs when no specific job_id is requested.
            # OLD: No is_hidden filter → hidden auto-restart jobs would overwrite manual scan results.
            # Auto-restart scans (is_hidden=True) complete with potentially fewer/no results, 
            # causing the "vanishing stocks" UI bug where manual scan results disappear 
            # when the newer auto-scan finishes with empty data.
            query = select(Job).where(
                Job.type == job_type, 
                Job.status == "completed",
                Job.is_hidden == False,
                Job.created_at >= since
            ).order_by(
                Job.updated_at.desc()
            ).limit(1)
            res = await db.execute(query)
            valid_job = res.scalars().first()
        
        if not valid_job:
            return sanitize_json_data({"buys": [], "sells": [], "holds": [], "total_count": 0, "stats": {}})

        # Unified Pulse Statistics (IST)
        stats = get_job_pulse_stats(valid_job)
        
        data = valid_job.result.get("data", [])
        # [V14.6 SEQUENCE-AWARE SORTING] Descending Score, then Ascending Analysis Index
        def sort_key(x): return (x.get("score", 0), -(x.get("analysis_index", 0)))
        
        buys = sorted([s for s in data if s.get("signal") in ["BUY", "BUY_STRONG"]], key=sort_key, reverse=True)[:100]
        sells = sorted([s for s in data if s.get("signal") in ["SELL", "SELL_STRONG"]], key=sort_key, reverse=True)[:100]
        holds = sorted([s for s in data if s.get("signal") in ["NEUTRAL", "HOLD"]], key=sort_key, reverse=True)[:100]
        
        return sanitize_json_data({
            "buys": buys,
            "sells": sells,
            "holds": holds,
            "total_count": len(data),
            "stats": stats
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return sanitize_json_data({"buys": [], "sells": [], "holds": [], "stats": {}})

@router.get("/sectors")
async def get_sector_signals(
    mode: str = "longterm", 
    job_id: str = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns signals grouped by industry sectors for heatmaps.
    """
    try:
        if mode == "longterm": job_type = "full_scan"
        elif mode == "swing": job_type = "swing_scan"
        else: job_type = "intraday"
        
        from datetime import datetime, timedelta
        since = datetime.utcnow() - timedelta(hours=24)
        
        # [V14.7 DIRECT LOCKING] Use specific Job ID if provided by the UI
        if job_id:
            valid_job = await db.get(Job, job_id)
        else:
            # [V30 FIX] Filter hidden auto-restart jobs (same fix as /today)
            query = select(Job).where(
                Job.type == job_type, 
                Job.status == "completed",
                Job.is_hidden == False,
                Job.created_at >= (datetime.utcnow() - timedelta(hours=24))
            ).order_by(
                Job.updated_at.desc()
            ).limit(1)
            res = await db.execute(query)
            valid_job = res.scalars().first()
            
        if not valid_job:
            return sanitize_json_data({"data": {}, "stats": {}})

        # Unified Pulse Statistics (IST)
        stats = get_job_pulse_stats(valid_job)
        data = valid_job.result.get("data", [])
        
        # Dynamic Aggregation
        response = {}
        for stock_data in data:
            try:
                sym = stock_data.get("symbol", "UNKNOWN")
                sector = stock_data.get("sector")
                
                if not sector or sector == "Unknown":
                    sector = market_service.get_sector_for_symbol(sym)
                
                if sector not in response:
                    response[sector] = {"buys": [], "sells": [], "holds": []}
                
                signal = stock_data.get("signal")
                if signal in ["BUY", "BUY_STRONG"]:
                    response[sector]["buys"].append(stock_data)
                elif signal in ["SELL", "SELL_STRONG"]:
                    response[sector]["sells"].append(stock_data)
                elif signal in ["NEUTRAL", "HOLD"]:
                    response[sector]["holds"].append(stock_data)
            except: continue
            
        return sanitize_json_data({
            "data": response,
            "stats": stats
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return sanitize_json_data({"data": {}, "stats": {}})

@router.get("/quick_scan/{symbol}")
@router.get("/analyze/{symbol}")
@router.get("/{symbol}")
async def analyze_stock(symbol: str, mode: str = "longterm"):
    """
    On-demand analysis for deep clarity on a single stock.
    Supports both 'longterm' and 'intraday' modes.
    """
    sym = symbol.strip().upper()
    candidates = []
    
    # [V45] Smart Ticker Resolution (Map Company Name to Ticker)
    import json
    import os
    json_path = os.path.join("app", "data", "nifty500.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                nifty_data = json.load(f)
                for item in nifty_data:
                    item_name = item.get("name", "").upper()
                    item_sym = item.get("symbol", "").upper()
                    
                    # Exact ticker match first
                    if sym == item_sym or sym == item_sym.replace(".NS", ""):
                        if item_sym not in candidates: candidates.insert(0, item_sym)
                    # Name match (e.g. "INFOSYS" in "INFOSYS LTD.")
                    elif len(sym) >= 3 and sym in item_name:
                        if item_sym not in candidates: candidates.append(item_sym)
        except Exception as e:
            print(f"Error resolving ticker from name: {e}")
            
    # Fallbacks if not found in list
    if not candidates:
        if "." not in sym:
            candidates = [f"{sym}.NS", f"{sym}.BO", sym]
        else:
            candidates = [sym]
        
    print(f"📡 Real-Time Analysis: {sym} in {mode} mode")
    analysis = None
    
    for s in candidates:
        try:
            if mode == "intraday":
                analysis = await intraday_engine.analyze_stock(s)
            elif mode == "swing":
                # Ensure Swing mode uses the specialized Swing Engine
                from app.services.swing_engine import swing_engine
                analysis = await swing_engine.analyze_stock(s)
            else:
                # 1. Fetch Market Context (Regime & Macro) to ensure scoring alignment with Scan
                regime = await longterm_scanner_engine._detect_market_regime()
                macro = await longterm_scanner_engine._detect_macro_regime()
                
                # 2. Analyze with context
                analysis = await longterm_scanner_engine.analyze_stock(
                    s, 
                    weights=regime["weights"], 
                    regime_label=regime["label"], 
                    macro_data=macro,
                    fast_fail=False
                )
            if analysis and "skip_reason" not in analysis: 
                break
            else:
                if analysis and "skip_reason" in analysis:
                    print(f"Engine ({mode}) skipped {s}: {analysis['skip_reason']}")
                analysis = None # Reset for next candidate

        except Exception as e:
            print(f"Engine ({mode}) failed for {s}: {e}")
            continue
            
    if not analysis:
        return {"error": "Symbol not found or data unavailable", "symbol": symbol, "mode": mode}
        
    return sanitize_json_data(analysis)

@router.get("/portfolio")
async def get_portfolio_analysis(mode: str = "longterm", db: AsyncSession = Depends(get_db)):
    try:
        if mode == "longterm": job_type = "full_scan"
        elif mode == "swing": job_type = "swing_scan"
        else: job_type = "intraday"
        query = select(Job).where(
            Job.type == job_type, 
            Job.status.in_(["completed", "processing"])
        ).order_by(
            Job.result.isnot(None).desc(), 
            Job.updated_at.desc()
        ).limit(1)
        result = await db.execute(query)
        job = result.scalars().first()
        
        if not job or not job.result:
            return {"message": "No scan data found."}
            
        data = job.result.get("data", [])
        if not data: return {"message": "Empty scan results."}
        
        top_buys = sorted([s for s in data if s.get("signal") == "BUY"], 
                          key=lambda x: x.get("score", 0), reverse=True)[:100]
        
        if not top_buys: return {"message": "Not enough BUY signals found."}
            
        analysis = portfolio_engine.analyze_portfolio(top_buys)
        symbols = [s["symbol"] for s in top_buys]
        price_tasks = {s: market_service.get_ohlc(s, period="1y") for s in symbols}
        price_results = await asyncio.gather(*price_tasks.values())
        price_map = dict(zip(symbols, price_results))
        
        corr_matrix = await portfolio_engine.calculate_correlation_matrix(price_map)
        analysis["correlation_matrix"] = corr_matrix
        
        return sanitize_json_data(analysis)
    except Exception as e:
        return {"error": str(e)}
