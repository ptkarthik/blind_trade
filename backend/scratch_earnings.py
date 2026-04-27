import yfinance as yf
from datetime import datetime

t = yf.Ticker("RELIANCE.NS")
print("--- Calendar ---")
try:
    print(t.calendar)
except Exception as e:
    print(f"Error calendar: {e}")

print("--- Earnings Dates ---")
try:
    print(t.get_earnings_dates(limit=5))
except Exception as e:
    print(f"Error dates: {e}")
