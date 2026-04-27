import yfinance as yf

t = yf.Ticker("RELIANCE.NS")
info = t.info
print({k: v for k, v in info.items() if 'earn' in k.lower() or 'date' in k.lower()})

t2 = yf.Ticker("AAPL")
info2 = t2.info
print({k: v for k, v in info2.items() if 'earn' in k.lower() or 'date' in k.lower()})

