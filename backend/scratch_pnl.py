import yfinance as yf
import pandas as pd

symbols = {
    "SOUTHBANK.NS": 59.52,
    "SASKEN.NS": 1293.70,
    "NEWGEN.NS": 476.45,
    "KPIGREEN.NS": 461.00,
    "LATENTVIEW.NS": 294.60,
    "BHARATSE.NS": 174.45,
    "ASAHIINDIA.NS": 845.15,
    "BANSALWIRE.NS": 310.30
}

print("Fetching REAL prices for your positions...\n")
for sym, buy_price in symbols.items():
    try:
        t = yf.Ticker(sym)
        # Get the very latest price
        h = t.history(period="1d", interval="1m")
        if not h.empty:
            live_price = float(h['Close'].iloc[-1])
            pnl_pct = ((live_price - buy_price) / buy_price) * 100
            status = "PROFIT" if pnl_pct > 0 else "LOSS" if pnl_pct < 0 else "FLAT"
            print(f"{sym}: Buy={buy_price:.2f} | Live={live_price:.2f} | PnL: {pnl_pct:+.2f}% ({status})")
        else:
            print(f"{sym}: Failed to fetch live data.")
    except Exception as e:
        print(f"{sym}: Error {e}")
