import yfinance as yf
import pandas as pd
import datetime

print("Fetching directly from yfinance...")
df = yf.download("ADORWELD.NS", period="5d", interval="15m")
if not df.empty:
    print(df.tail(20)[['Open', 'High', 'Low', 'Close', 'Volume']])
else:
    print("Empty dataframe.")
