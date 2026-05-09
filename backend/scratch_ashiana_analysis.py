import asyncio
import pandas as pd
from datetime import datetime
import sys
import os

sys.path.append(r"C:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend")

from app.services.market_data import market_service
from app.services.intraday_engine import intraday_engine
from app.services.ta_intraday import ta_intraday

async def analyze_ashiana():
    symbol = "ASHIANA.NS"
    print(f"--- Analyzing {symbol} Intraday ---")
    
    df_15m = await market_service.get_ohlc(symbol, period="5d", interval="15m")
    if df_15m is None or df_15m.empty:
        print("Failed to fetch 15m data.")
        return
        
    df_15m.attrs["symbol"] = symbol
    
    df_1h = await market_service.get_ohlc(symbol, period="1mo", interval="1h")
    if df_1h is not None:
        df_1h.attrs["symbol"] = symbol
        
    today_dates = pd.Series(df_15m.index.date).unique()
    last_day = today_dates[-1]
    print(f"Target Date: {last_day}\n")
    
    today_df = df_15m[df_15m.index.date == last_day]
    
    print(f"{'Time':<10} | {'Price':<8} | {'EMA20':<8} | {'ATR Stretch':<12} | {'Exhausted?':<12} | {'Pullback?':<10} | {'Alpha Mode':<15}")
    print("-" * 90)
    
    for i in range(0, len(today_df)):
        current_time = today_df.index[i]
        sim_df_15m = df_15m[df_15m.index <= current_time].copy()
        sim_df_1h = df_1h[df_1h.index <= current_time].copy() if df_1h is not None else None
        
        sim_df_15m.attrs["symbol"] = symbol
        if sim_df_1h is not None:
            sim_df_1h.attrs["symbol"] = symbol
            
        try:
            # Generate indicators
            ind = intraday_engine._compute_indicators(sim_df_15m)
            ind = intraday_engine._add_1h_context(ind, sim_df_1h)
            
            price = ind.get('price', 0)
            ema20 = ind.get('ema20', 0)
            exhaust_dict = ind.get('exhaustion', {})
            atr_dist = exhaust_dict.get('atr_dist', 0)
            is_exhausted = exhaust_dict.get('is_exhausted', False)
            is_pullback = ind.get('is_pullback', False)
            
            # Run layers to see what Alpha Mode it got assigned
            l1_score, l1_data = intraday_engine._run_layer1(ind)
            ind["l1_score"] = l1_score
            l2_score, l2_data = intraday_engine._run_layer2(ind, sim_df_15m)
            
            alpha_mode = l2_data.get("mode", "NONE")
            if is_exhausted and "reasons" in exhaust_dict:
                ex_reason = exhaust_dict["reasons"][0] if exhaust_dict["reasons"] else ""
            else:
                ex_reason = ""
                
            time_str = current_time.strftime('%H:%M')
            print(f"{time_str:<10} | {price:<8.2f} | {ema20:<8.2f} | {atr_dist:<12.2f} | {str(is_exhausted):<12} | {str(is_pullback):<10} | {alpha_mode:<15}")
            if is_exhausted:
                print(f"  -> Reason: {ex_reason}")
                
        except Exception as e:
            print(f"Error at {current_time}: {e}")

if __name__ == "__main__":
    asyncio.run(analyze_ashiana())
