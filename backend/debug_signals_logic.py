
import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy.future import select
from app.services.market_data import market_service
import json

async def debug_signals():
    print("--- Debugging Signals Logic ---")
    
    # 1. Fetch Data like endpoints/signals.py
    async with AsyncSessionLocal() as session:
        stmt = select(Job).where(Job.status == "completed").order_by(Job.created_at.desc()).limit(1)
        res = await session.execute(stmt)
        job = res.scalars().first()
        data = job.result.get("data", [])
        
    print(f"Loaded {len(data)} items from DB.")
    
    # 2. Simulate Grouping
    sectors = ["Banking", "Finance", "IT", "Auto", "Pharma", "Energy", "FMCG", "Metal", "Infrastructure", "Realty", "Services"]
    response = {s: {"buys": [], "sells": []} for s in sectors}
    
    mappings = []
    
    for stock_data in data[:5]: # Check first 5
        sym = stock_data["symbol"]
        signal = stock_data["signal"]
        
        # LOGIC FROM SIGNALS.PY
        sector = stock_data.get("sector")
        source = "DB"
        
        if not sector or sector == "Unknown":
            sector = market_service.SECTOR_MAP.get(sym, "Services")
            source = "MAP"
            
        # Normalization
        final_sector = sector
        if sector not in response:
            if "Bank" in sector: final_sector = "Banking"
            elif "Tech" in sector: final_sector = "IT"
            # ... (expanded logic)
        
        mappings.append(f"{sym} -> {sector} ({source}) -> Final: {final_sector}")
        
        if final_sector in response:
            response[final_sector]["buys" if signal == "BUY" else "sells"].append(sym)
            
    print("\n--- Mappings ---")
    for m in mappings:
        print(m)
        
    print("\n--- Result Groups ---")
    for s, v in response.items():
        if v["buys"] or v["sells"]:
            print(f"{s}: {len(v['buys'])} buys, {len(v['sells'])} sells")

if __name__ == "__main__":
    asyncio.run(debug_signals())
