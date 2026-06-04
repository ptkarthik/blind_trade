import asyncio
import aiohttp

async def run():
    async with aiohttp.ClientSession() as s:
        u = 'https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_03062026.csv'
        async with s.get(u, headers={'User-Agent': 'Mozilla/5.0'}) as r:
            text = await r.text()
            print('2026 code:', r.status, 'len:', len(text))
            if len(text) > 0:
                print('Content:', text[:100])

asyncio.run(run())
