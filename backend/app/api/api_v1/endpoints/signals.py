
from fastapi import APIRouter, Depends
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.job import Job
from app.services.market_data import market_service
from app.services.scanner_engine import scanner_engine
from app.services.intraday_engine import intraday_engine
from app.services.portfolio_engine import portfolio_engine
import asyncio
import numpy as np

router = APIRouter()

def sanitize_json_data(data):
    try:
        if data is None: return 0.0
        if isinstance(data, str):
            if data.upper() in ["N/A", "NAN", "INF", "-INF", "NONE", ""]: return 0.0
            return data
        if isinstance(data, (float, np.floating)):
            if np.isnan(data) or np.isinf(data): return 0.0
            return float(data)
        if isinstance(data, dict):
            return {k: sanitize_json_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [sanitize_json_data(i) for i in data]
        elif isinstance(data, (np.integer, int)):
            return int(data)
        if hasattr(data, "item"): return sanitize_json_data(data.item())
    except:
        return 0.0
    return data

@router.get("/today")
async def get_todays_signals(mode: str = "longterm", db: AsyncSession = Depends(get_db)):
    """
    Returns structured Top 100 buys, sells, holds for the dashboard.
    """
    try:
        job_type = "full_scan" if mode == "longterm" else "intraday"
        
        query = select(Job).where(Job.type == job_type, Job.status == "completed").order_by(Job.updated_at.desc()).limit(1)
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
        query = select(Job).where(Job.type == job_type, Job.status == "completed").order_by(Job.updated_at.desc()).limit(1)
        res = await db.execute(query)
        valid_job = res.scalars().first()
        
        sectors = ["Banking", "Finance", "IT", "Auto", "Pharma", "Energy", "FMCG", "Metal", "Infrastructure", "Realty", "Services", "General"]
        response = {s: {"buys": [], "sells": [], "holds": [], "last_updated": "Never"} for s in sectors}

        if not valid_job or not valid_job.result:
            return response
            
        data = valid_job.result.get("data", [])
        
        timestamp = ""
        if valid_job.updated_at:
            try:
                import datetime
                ist_time = valid_job.updated_at + datetime.timedelta(hours=5, minutes=30)
                timestamp = ist_time.strftime("%d %b, %H:%M:%S")
            except:
                 timestamp = valid_job.updated_at.strftime("%H:%M:%S")
        
        for stock_data in data:
            try:
                sym = stock_data.get("symbol", "UNKNOWN")
                sector = stock_data.get("sector")
                if not sector or sector == "Unknown" or sector == "General":
                    sector = market_service.get_sector_for_symbol(sym)
                    stock_data["sector"] = sector
                    
                if sector not in response:
                    sector = "General"
                
                signal = stock_data.get("signal")
                if signal == "BUY":
                    response[sector]["buys"].append(stock_data)
                elif signal == "SELL":
                    response[sector]["sells"].append(stock_data)
                elif signal == "NEUTRAL":
                    response[sector]["holds"].append(stock_data)
            except: continue

        for s in response:
            response[s]["last_updated"] = timestamp
            
        return sanitize_json_data(response)
    except Exception as e:
        print(f"Sector signals crash: {e}")
        return {}

@router.get("/quick_scan/{symbol}")
@router.get("/analyze/{symbol}")
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
                analysis = await intraday_engine.analyze_stock(s)
            else:
                analysis = await scanner_engine.analyze_stock(s)
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
        query = select(Job).where(Job.type == job_type, Job.status.in_(["completed", "processing"])).order_by(Job.created_at.desc()).limit(1)
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
