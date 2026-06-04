import asyncio
from app.services.kite_data import kite_data
import yfinance as yf

async def test():
    await kite_data.initialize()
    if kite_data.is_ready:
        print("Kite fetching...")
        df = await kite_data.fetch_ohlc('SUVEN.NS', period='1d', interval='1d')
        if df is not None and not df.empty:
            print("KITE LAST CLOSE:", df['close'].iloc[-1])
        else:
            print("Kite returned empty")
    else:
        print("Kite not ready")

    try:
        yf_df = yf.Ticker('SUVEN.NS').history(period='1d')
        print("YAHOO LAST CLOSE:", yf_df['Close'].iloc[-1])
    except Exception as e:
        print("Yahoo failed:", e)

if __name__ == "__main__":
    asyncio.run(test())
