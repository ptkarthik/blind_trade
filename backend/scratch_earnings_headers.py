import yfinance as yf
import requests

def _make_session():
    s = requests.Session()
    s.verify = True
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "*/*", "Connection": "close"})
    return s

try:
    print("Testing info...")
    t = yf.Ticker("RELIANCE.NS", session=_make_session())
    inf = t.info
    print(inf.get('earningsTimestamp'))
    print(inf.get('earningsTimestampStart'))
    print(inf.get('earningsTimestampEnd'))
except Exception as e:
    print(e)
