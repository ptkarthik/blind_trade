import asyncio
from app.services.ai_brain import ai_brain
from dotenv import load_dotenv

load_dotenv()

async def test():
    symbol = "RELIANCE.NS"
    strategy = "BREAKOUT"
    current_price = 3000.50
    
    # Mock mathematical reasons from the engine
    reasons = [
        {"text": "Fresh 20-Day Breakout", "label": "BREAKOUT", "type": "positive"},
        {"text": "Bullish Momentum Supported", "label": "RSI", "type": "positive"},
        {"text": "MACD Bullish (Expanding)", "label": "MACD", "type": "positive"}
    ]
    
    # Mock raw technical data
    indicators = {
        "rsi": 65.2,
        "adx": 32.5,
        "macd_line": 15.2,
        "macd_signal": 10.1,
        "volatility_ratio": 1.5,
        "sma_50": 2850.0,
        "ema_20": 2900.0,
        "volume_surge_multiplier": 2.1
    }
    
    print(f"Testing AI Brain connection for {symbol}...")
    result = await ai_brain.analyze_trade_setup(symbol, strategy, current_price, indicators, reasons)
    
    print("\n--- AI Result ---")
    import json
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(test())
