
import asyncio
import sys
import os

# Set up paths to import the app
sys.path.append(os.getcwd())

from app.services.scanner_engine import scanner_engine
from app.services.market_data import market_service

async def test_entry_logic(symbol):
    try:
        res = await scanner_engine.analyze_stock(symbol)
        if res:
            price = res.get('price')
            entry = res.get('entry')
            advisory = res.get('investment_advisory', {})
            entry_analysis = advisory.get('entry_analysis', {})
            
            output = f"[{symbol}] Current Price: ₹{price}\n"
            output += f"Smart Entry: ₹{entry} ({entry_analysis.get('entry_type')})\n"
            output += f"Rationale: {entry_analysis.get('rationale')}\n"
            output += f"Buffer: {entry_analysis.get('buffer_pct')}% below market\n"
            return output
        else:
            return f"Failed to analyze {symbol}\n"
    except Exception as e:
        return f"Error analyzing {symbol}: {e}\n"

async def main():
    await market_service.initialize()
    # Testing with a few diverse symbols
    out1 = await test_entry_logic("PTC.NS")
    out2 = await test_entry_logic("RELIANCE.NS")
    out3 = await test_entry_logic("RVNL.NS") # Likely momentum
    
    with open("verification_entry.txt", "w", encoding="utf-8") as f:
        f.write(out1 + "\n" + out2 + "\n" + out3)
    
    print("Verification complete. Check verification_entry.txt")

if __name__ == "__main__":
    asyncio.run(main())
