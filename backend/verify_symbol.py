
import asyncio
from app.services.scanner_engine import scanner_engine
from app.services.market_data import market_service
import json

async def verify_signal(symbol):
    print(f"--- Verifying {symbol} ---")
    try:
        # Mocking the weights and regime since we are calling it directly
        regime = {
            "label": "Bullish (Gaining Momentum)", # Standard bullish regime
            "weights": {
                "fundamental": 0.30, "trend": 0.35, "momentum": 0.20, "volume": 0.10, "risk": 0.05
            }
        }
        
        result = await scanner_engine.analyze_stock(
            symbol, 
            weights=regime["weights"], 
            regime_label=regime["label"]
        )
        
        if result:
            print(f"Signal: {result['signal']}")
            print(f"Score: {result['score']}")
            print(f"Strategic Verdict: {result['strategic_summary']}")
            print(f"TOP 5 REASONS:")
            for r in result['reasons']:
                color = "🔴" if r.get("type") == "negative" else "🟢"
                print(f" {color} {r.get('text')} ({r.get('label')})")
        else:
            print(f"No result returned for {symbol}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Test a few symbols: 
    # NILKAMAL (previously a SELL)
    # ITC (the user's example)
    # PFC (previously a BUY)
    asyncio.run(verify_signal("NILKAMAL"))
    asyncio.run(verify_signal("ITC"))
    asyncio.run(verify_signal("PFC"))
