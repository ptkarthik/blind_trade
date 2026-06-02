"""Direct test: Is kite_data actually ready in a fresh import?"""
import asyncio
import sys, os
sys.path.insert(0, os.getcwd())

# Bypass proxies
os.environ['NO_PROXY'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

async def main():
    from app.services.kite_data import kite_data
    
    print(f"1. Before init: is_ready = {kite_data.is_ready}")
    print(f"   _is_ready = {kite_data._is_ready}")
    print(f"   _access_token = {'SET' if kite_data._access_token else 'NONE'}")
    print(f"   _kite = {'SET' if kite_data._kite else 'NONE'}")
    
    # Try initializing
    await kite_data.initialize()
    
    print(f"\n2. After init: is_ready = {kite_data.is_ready}")
    print(f"   _is_ready = {kite_data._is_ready}")
    print(f"   _access_token = {'SET' if kite_data._access_token else 'NONE'}")
    print(f"   instruments count = {len(kite_data._instruments)}")
    
    if kite_data.is_ready:
        result = await kite_data.get_ltp(['ASTERDM.NS'])
        print(f"\n3. LTP Result: {result}")
    else:
        print("\n3. KITE NOT READY - this is why prices are stuck!")

asyncio.run(main())
