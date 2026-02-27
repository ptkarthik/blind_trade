import yfinance as yf
print("Testing yfinance download...")
df = yf.download("^NSEI", period="2d", interval="15m")
print(len(df))
