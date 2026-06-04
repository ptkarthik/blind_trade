import asyncio
import sys
sys.path.insert(0, '.')

async def main():
    from app.services.kite_data import kite_data
    await kite_data.initialize()
    
    if not kite_data.is_ready:
        print('Kite not ready')
        return
    
    test_symbols = ['TRITURBINE.NS', 'SUVEN.NS', 'RELIANCE.NS']
    
    # Test get_token for each
    for sym in test_symbols:
        token = kite_data.get_token(sym)
        print(f'Token for {sym}: {token}')
    
    # Test get_ltp with a LIST (not a string)
    print('\n--- Testing get_ltp with list ---')
    result = await kite_data.get_ltp(test_symbols)
    print(f'get_ltp result: {result}')
    
    for sym, data in result.items():
        print(f'  {sym}: LTP=₹{data.get("price", "N/A")}, Change={data.get("change_percent", "N/A")}%')

asyncio.run(main())
