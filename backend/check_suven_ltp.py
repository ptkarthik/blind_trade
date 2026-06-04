import asyncio
import sys
sys.path.insert(0, '.')

async def main():
    from app.services.kite_data import kite_data
    await kite_data.initialize()
    if kite_data.is_ready:
        ltp = await kite_data.get_ltp('SUVEN.NS')
        print(f'Kite LTP: {ltp}')
        df = await kite_data.fetch_ohlc('SUVEN.NS', period='1y', interval='1d')
        if df is not None and not df.empty:
            last_close = df['close'].iloc[-1]
            last_date = df.index[-1]
            print(f'Kite Last Daily Close: {last_close}')
            print(f'Date of last candle: {last_date}')
    else:
        print('Kite not ready')

asyncio.run(main())
