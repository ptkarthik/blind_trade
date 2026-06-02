import asyncio
from app.services.intraday_engine import intraday_engine
import traceback

async def test_supriya():
    print("Analyzing SUPRIYA.NS...")
    
    # Temporarily monkey patch analyze_stock to not catch the exception and print traceback
    original_analyze_stock = intraday_engine.analyze_stock
    
    async def debug_analyze_stock(sym, *args, **kwargs):
        try:
            return await original_analyze_stock(sym, *args, **kwargs)
        except Exception as e:
            traceback.print_exc()
            raise e
            
    try:
        # Actually, analyze_stock catches it internally. Let's just run it and see.
        # But wait, it returns "System Error: ...". To see the traceback, we need to modify the file temporarily.
        pass
    except Exception as e:
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_supriya())
