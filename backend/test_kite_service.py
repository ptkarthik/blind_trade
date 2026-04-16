import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

async def test_kite_tradability():
    from app.services.kite_service import kite_service
    
    print("Synchronizing Kite Margins...")
    await kite_service.initialize()
    
    test_symbols = ["RELIANCE.NS", "ZOMATO.NS", "CEIGALL.NS", "GTLINFRA.NS", "TCS.NS"]
    
    print("\n--- Tradability Audit Results ---")
    for sym in test_symbols:
        audit = kite_service.get_tradability(sym)
        status = "BLOCKED" if audit["is_kite_restricted"] else "ALLOWED"
        mult = audit.get("multiplier", 1.0)
        print(f"{sym:12} | {status:8} | Mult: {mult:4}x | Reason: {audit.get('reason')}")

if __name__ == "__main__":
    asyncio.run(test_kite_tradability())
