"""Simulate exactly what the /trades endpoint does."""
import asyncio, sys, os
sys.path.insert(0, os.getcwd())
os.environ['NO_PROXY'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

async def main():
    # Step 1: Import kite_data (same singleton the API uses)
    from app.services.kite_data import kite_data
    print(f"Step 1 - Raw import state: is_ready={kite_data.is_ready}, token={'SET' if kite_data._access_token else 'NONE'}, kite={'SET' if kite_data._kite else 'NONE'}")
    
    # Step 2: What happens if we DON'T initialize (like the /trades endpoint)
    # The /trades endpoint does NOT call initialize() - it just checks is_ready
    if kite_data.is_ready:
        print("Step 2 - Kite IS ready without init. Fetching LTP...")
        result = await kite_data.get_ltp(['ASTERDM.NS'])
        print(f"  LTP: {result}")
    else:
        print("Step 2 - Kite is NOT ready without init!")
        print("  This is the bug: /trades checks is_ready but it's False because")
        print("  kite_data was never initialized in this process.")
        
        # Step 3: Now initialize and try again
        print("\nStep 3 - Initializing kite_data...")
        await kite_data.initialize()
        print(f"  After init: is_ready={kite_data.is_ready}")
        if kite_data.is_ready:
            result = await kite_data.get_ltp(['ASTERDM.NS'])
            print(f"  LTP: {result}")

asyncio.run(main())
