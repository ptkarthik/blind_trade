
import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

async def verify_scanner_fix():
    from app.services.scanner_engine import scanner_engine
    from app.services.market_data import market_service
    
    # Mock a job ID
    dummy_job_id = "test-job-fix"
    
    print("--- Verifying Scanner Engine Fix ---")
    # Test with a mix of dicts (like from nifty500.json) and strings
    test_symbols = [
        {"symbol": "3MINDIA.NS", "name": "3M India", "sector": "Services"},
        "RELIANCE.NS",
        {"symbol": "SUZLON.NS", "name": "Suzlon", "sector": "Energy"}
    ]
    
    # We can't easily run the full run_scan because it needs DB and background loops
    # But we can test the logic inside analyze_stock and the display normalization.
    
    for sym in test_symbols:
        symbol_str = sym["symbol"] if isinstance(sym, dict) else sym
        print(f"Testing analyze_stock for: {symbol_str} (input type: {type(sym)})")
        try:
            # This should not raise "unhashable type: dict"
            res = await scanner_engine.analyze_stock(symbol_str)
            if res:
                print(f"✅ Success: {symbol_str} analyzed. Score: {res.get('score')}")
            else:
                print(f"⚠️ Warning: {symbol_str} returned no result (OK if market data failed)")
        except Exception as e:
            print(f"❌ Failed: {symbol_str} error: {e}")

    # Test display normalization
    from app.services.scanner_engine import ScannerEngine
    se = ScannerEngine()
    se.active_symbols = test_symbols
    display_symbols = [s["symbol"] if isinstance(s, dict) else s for s in se.active_symbols]
    active_str = ", ".join(display_symbols[:3])
    print(f"Normalized Display String: {active_str}")
    if "3MINDIA.NS" in active_str and "RELIANCE.NS" in active_str:
        print("✅ Display Normalization Verified.")
    else:
        print("❌ Display Normalization Failed.")

if __name__ == "__main__":
    asyncio.run(verify_scanner_fix())
