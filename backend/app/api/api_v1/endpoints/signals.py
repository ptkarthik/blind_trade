from fastapi import APIRouter, Depends
from sqlalchemy import func
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

router = APIRouter()

def sanitize_json_data(data):
    """
    Optimized for Speed: Data is already sanitized during the scan process 
    before being saved to the database. Bypassing second-pass recursion here 
    significantly improves UI responsiveness during mode toggles.
    """
    return data

@router.get("/today")
async def get_todays_signals(mode: str = "longterm", db: AsyncSession = Depends(get_db)):
    """
    Returns structured Top 100 buys, sells, holds for the dashboard.
    """
    try:
        job_type = "full_scan" if mode == "longterm" else "intraday"
        
        # Allow results from completed, processing (live), and stopped (partial) jobs
        # Favor jobs that actually have results data, then order by most recent
        query = select(Job).where(
            Job.type == job_type, 
            Job.status.in_(["completed", "processing", "stopped"])
        ).order_by(
            Job.result.isnot(None).desc(), 
            Job.updated_at.desc()
        ).limit(1)
        res = await db.execute(query)
        valid_job = res.scalars().first()
        
        if not valid_job:
             return sanitize_json_data({"buys": [], "sells": [], "holds": [], "total_count": 0, "message": f"No completed {mode} scan found."})

        if not valid_job or not valid_job.result:
             return sanitize_json_data({"buys": [], "sells": [], "holds": [], "total_count": 0})

        data = valid_job.result.get("data", [])
        buys = sorted([s for s in data if s.get("signal") == "BUY"], key=lambda x: x.get("score", 0), reverse=True)[:100]
        sells = sorted([s for s in data if s.get("signal") == "SELL"], key=lambda x: x.get("score", 0), reverse=True)[:100]
        holds = sorted([s for s in data if s.get("signal") == "NEUTRAL"], key=lambda x: x.get("score", 0), reverse=True)[:100]
        
        return sanitize_json_data({
            "buys": buys,
            "sells": sells,
            "holds": holds,
            "total_count": len(data)
        })
    except Exception as e:
        print(f"CRASH in get_todays_signals: {e}")
        return sanitize_json_data({"buys": [], "sells": [], "holds": []})

@router.get("/sectors")
async def get_sector_signals(mode: str = "longterm", db: AsyncSession = Depends(get_db)):
    """
    Returns signals grouped by industry sectors for heatmaps.
    """
    try:
        job_type = "full_scan" if mode == "longterm" else "intraday"
        # Allow results from completed, processing (live), and stopped (partial) jobs
        # SMARTER PICK: Favor jobs that actually have result data, then by latest update.
        # This prevents a fresh 0% scan from 'masking' the results of a 90% scan.
        query = select(Job).where(
            Job.type == job_type, 
            Job.status.in_(["completed", "processing", "stopped"])
        ).order_by(
            (func.json_extract(Job.result, '$.sectors').isnot(None)).desc(),
            (func.json_extract(Job.result, '$.data').isnot(None)).desc(),
            Job.updated_at.desc()
        ).limit(1)
        res = await db.execute(query)
        valid_job = res.scalars().first()
        
        if not valid_job or not valid_job.result:
            return {}
            
        # FAST PATH: Use pre-calculated sectors if available (O(1) fetch)
        if "sectors" in valid_job.result:
            return sanitize_json_data(valid_job.result["sectors"])

        data = valid_job.result.get("data", [])
        
        timestamp = ""
        if valid_job.updated_at:
            try:
                import datetime
                ist_time = valid_job.updated_at + datetime.timedelta(hours=5, minutes=30)
                timestamp = ist_time.strftime("%d %b, %H:%M:%S")
            except:
                 timestamp = valid_job.updated_at.strftime("%H:%M:%S")
        
        # Dynamic Aggregation
        response = {}
        
        for stock_data in data:
            try:
                sym = stock_data.get("symbol", "UNKNOWN")
                sector = stock_data.get("sector")
                
                # Fallback to Market Service if sector is missing in job result
                if not sector or sector == "Unknown":
                    sector = market_service.get_sector_for_symbol(sym)
                    stock_data["sector"] = sector
                
                # Default bucket if still unknown
                if not sector: sector = "General"
                
                # Initialize sector bucket if new
                if sector not in response:
                    response[sector] = {"buys": [], "sells": [], "holds": [], "last_updated": timestamp}
                
                signal = stock_data.get("signal")
                if signal == "BUY":
                    response[sector]["buys"].append(stock_data)
                elif signal == "SELL":
                    response[sector]["sells"].append(stock_data)
                elif signal == "NEUTRAL":
                    response[sector]["holds"].append(stock_data)
            except: continue
            
        return sanitize_json_data(response)
    except Exception as e:
        print(f"Sector signals crash: {e}")
        return {}

@router.get("/quick_scan/{symbol}")
@router.get("/analyze/{symbol}")
@router.get("/{symbol}")
async def analyze_stock(symbol: str, mode: str = "longterm"):
    """
    On-demand analysis for deep clarity on a single stock.
    Supports both 'longterm' and 'intraday' modes.
    """
    sym = symbol.strip().upper()
    candidates = [sym]
    if "." not in sym:
        candidates = [f"{sym}.NS", f"{sym}.BO", sym]
        
    print(f"📡 Real-Time Analysis: {sym} in {mode} mode")
    analysis = None
    
    for s in candidates:
        try:
            if mode == "intraday":
                analysis = await intraday_engine.analyze_stock(s, fast_fail=True)
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
                    fast_fail=True
                )
            if analysis: break
        except Exception as e:
            print(f"Engine ({mode}) failed for {s}: {e}")
            continue
            
    if not analysis:
        return {"error": "Symbol not found or data unavailable", "symbol": symbol, "mode": mode}
        
    return sanitize_json_data(analysis)

@router.get("/portfolio")
async def get_portfolio_analysis(mode: str = "longterm", db: AsyncSession = Depends(get_db)):
    try:
        job_type = "full_scan" if mode == "longterm" else "intraday"
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
