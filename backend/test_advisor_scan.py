
import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.scanner_engine import scanner_engine
from app.services.market_data import market_service
from app.db.session import engine, AsyncSessionLocal

async def test_advisor():
    print("--- Testing Advisor Engine Integration ---")
    
    # Analyze a stable stock (likely to have good data)
    symbol = "TCS" 
    print(f"Analyzing {symbol}...")
    
    # Initialize Market Data (Mock or Real)
    await market_service.initialize()
    
    # Run Analysis
    result = await scanner_engine.analyze_stock(symbol)
    
    if not result:
        print("❌ Analysis failed (returned None). Check headers/connection.")
        return

    print(f"\n✅ Analysis Successful for {symbol}")
    print(f"Score: {result.get('score')}")
    print(f"Verdict: {result.get('strategic_summary')}")
    
    advisory = result.get("investment_advisory")
    if advisory:
        print("\n--- Investment Advisory Report ---")
        
        hp = advisory.get("holding_period", {})
        print(f"📌 Suggested Hold: {hp.get('period_display')} ({hp.get('label')})")
        print(f"   Score: {hp.get('score')} | Components: {hp.get('components')}")
        
        tgt = advisory.get("targets", {})
        print(f"🎯 Dynamic Targets: 3-Year: {tgt.get('3_year_target')} (CAGR: {tgt.get('projected_cagr')}%)")
        print(f"   Logic: {tgt.get('blend_logic')}")
        
        sl = advisory.get("stop_loss", {})
        print(f"🛑 Smart Stop: {sl.get('stop_price')} ({sl.get('type')})")
        print(f"   Trailing: {sl.get('trailing_condition')}")
        
        scenarios = advisory.get("scenarios", [])
        print("\n🔮 Scenarios:")
        for s in scenarios:
            print(f"   - {s['label']}: Target {s['target']} (Upside {s['upside']}%)")
            
        trend = advisory.get("trend_status", {})
        print(f"\n📈 Trend: {trend.get('slope')} -> {trend.get('action')}")
        
        print(f"\n🔄 Review Cycle: {advisory.get('review_cycle')}")
    else:
        print("❌ 'investment_advisory' key missing in result!")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_advisor())
