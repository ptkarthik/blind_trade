import requests
r = requests.get('http://localhost:8012/api/v1/papertrades/trades', timeout=10)
trades = r.json()
print(f"Total trades returned: {len(trades)}")
for t in trades:
    if t.get('status') == 'OPEN':
        sym = t.get('symbol')
        buy = t.get('buy_price')
        live = t.get('current_price')
        src = t.get('price_source')
        is_live = t.get('is_live')
        print(f"  {sym}: Buy={buy} -> Live={live} Source={src} IsLive={is_live}")
    else:
        print(f"  {t.get('symbol')}: CLOSED sell={t.get('sell_price')}")
