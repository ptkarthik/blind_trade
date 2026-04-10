import sys
import pandas as pd
import yfinance as yf
import numpy as np
import asyncio

sys.path.append(r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend")
from app.services.intraday_engine import intraday_engine

def run_backtest():
    print("🔬 [PIONEER BACKTEST] Initiating Historical Matrix Simulation...")
    symbols = ["RELIANCE.NS", "ZOMATO.NS", "HDFCBANK.NS", "TATASTEEL.NS", "INFY.NS"]
    
    # We will track the distribution of signals
    distributions = {"BUY_STRONG": 0, "BUY": 0, "NEUTRAL": 0, "IGNORE": 0}
    layer_stats = {"L1_pass": 0, "L2_Alpha": 0, "L3_Penalties": 0, "Total_Scans": 0}
    
    for sym in symbols:
        print(f"📥 Fetching 5-Day 15m Data for {sym}...")
        try:
            df = yf.download(sym, period="5d", interval="15m", progress=False)
            df_1h = yf.download(sym, period="10d", interval="60m", progress=False)
        except Exception as e:
            print(f"Error fetching {sym}: {e}")
            continue
            
        if df.empty or len(df) < 25:
            continue
            
        # Normalize columns
        df.columns = [c.lower() for c in df.columns]
        df_1h.columns = [c.lower() for c in df_1h.columns]
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            df_1h.columns = df_1h.columns.get_level_values(0)

        total_candles = len(df)
        
        # Simulate walking forward through time (from candle 20 to the end)
        for i in range(25, total_candles):
            layer_stats["Total_Scans"] += 1
            df_slice = df.iloc[:i].copy()
            
            # Get 1h slice up to the current timestamp
            current_time = df_slice.index[-1]
            df_1h_slice = df_1h[df_1h.index <= current_time]
            if df_1h_slice.empty: continue
            
            try:
                indicators = intraday_engine._get_indicators(df_slice, df_1h_slice)
                if not indicators: continue
                
                # Check Trend Broken (Gate 0)
                if indicators["price"] < indicators["ema20"]:
                    distributions["IGNORE"] += 1
                    continue
                    
                # Layer 1
                l1_score, l1_data = intraday_engine._run_layer1(indicators)
                if l1_score < 13: # The new strictness gate
                    distributions["IGNORE"] += 1
                    continue
                    
                layer_stats["L1_pass"] += 1
                
                # Layer 2
                l2_score, l2_data = intraday_engine._run_layer2(indicators, df_slice, df_1h_slice)
                if l2_score > 0:
                    layer_stats["L2_Alpha"] += 1
                    
                # Layer 3
                l3_penalty, l3_data = intraday_engine._run_layer3(indicators, df_slice, None, l2_data)
                if l3_penalty > 0:
                    layer_stats["L3_Penalties"] += 1
                    
                final_score = max(0, min(100, (l1_score + l2_score - l3_penalty)))
                
                if final_score >= 85: distributions["BUY_STRONG"] += 1
                elif final_score >= 60: distributions["BUY"] += 1
                elif final_score >= 40: distributions["NEUTRAL"] += 1
                else: distributions["IGNORE"] += 1
                
            except Exception as e:
                # print(f"Math Error: {e}")
                pass

    print("\n" + "="*50)
    print("📊 BACKTEST RESULTS (Last 5 Trading Days | 5 Stocks)")
    print("="*50)
    
    print(f"Total Candlestick Datapoints Evaluated: {layer_stats['Total_Scans']}")
    print(f"\n🧠 LAYER RETENTION:")
    print(f" ├─ Survived Base Trend (>EMA20): {layer_stats['L1_pass']} instances")
    print(f" ├─ Achieved Alpha Edge (L2): {layer_stats['L2_Alpha']} instances")
    print(f" └─ Triggered L3 Penalties: {layer_stats['L3_Penalties']} instances")
    
    print(f"\n🎯 SIGNAL DISTRIBUTION:")
    for sig, count in distributions.items():
        pct = (count / max(layer_stats['Total_Scans'], 1)) * 100
        print(f" ├─ {sig:<12}: {count:<4} ({pct:.1f}%)")
        
    print("\n🛡️ PIONEER ANALYSIS:")
    buy_ratio = ((distributions['BUY_STRONG'] + distributions['BUY']) / max(layer_stats['Total_Scans'], 1)) * 100
    if buy_ratio < 1.0:
        print("💡 ENGINE IS EXTREMELY STRICT. Only the top 1% of institutional setups are passing.")
    elif buy_ratio < 5.0:
        print("💡 ENGINE IS BALANCED (Institutional Grade). Passing highly selective setups.")
    else:
        print("💡 ENGINE IS TOO LOOSE. Too many signals passing, recommend increasing Layer 3 penalties.")

if __name__ == "__main__":
    run_backtest()
