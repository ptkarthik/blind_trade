import asyncio
import pandas as pd
import numpy as np
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "app"))
sys.path.append(os.getcwd())

from app.services.ta_intraday import ta_intraday

async def test_logic():
    log_file = "test_results.log"
    with open(log_file, "w", encoding="utf-8") as f:
        def log(msg):
            print(msg)
            f.write(msg + "\n")
            
        log("🚀 Testing Refined Intraday Logic (Phase 2)...")
        
        # Create mock data: 50 candles (5m)
        # Strong Bullish Trend
        dates = pd.date_range("2026-03-12 09:15", periods=50, freq="5min")
        close_prices = np.linspace(100, 110, 50) + np.random.normal(0, 0.2, 50)
        high_prices = close_prices + 0.5
        low_prices = close_prices - 0.5
        open_prices = close_prices - 0.1
        volumes = np.random.randint(1000, 5000, 50)
        
        df = pd.DataFrame({
            "open": open_prices,
            "high": high_prices,
            "low": low_prices,
            "close": close_prices,
            "volume": volumes
        }, index=dates)
        
        log(f"Sample Data (Last 5):")
        log(str(df.tail()))
        
        analysis = ta_intraday.analyze_stock(df)
        
        log("\n--- Analysis Results ---")
        log(f"VWAP Score: {analysis.get('vwap_score')}")
        log(f"RVOL Score: {analysis.get('rvol_score')}")
        log(f"EMA Score: {analysis.get('ema_score')}")
        log(f"Pivot Score: {analysis.get('pivot_score')}")
        log(f"PA Score: {analysis.get('pa_score')}")
        
        log("\n--- Professional Indicators ---")
        # Verify ADX & Fan
        groups = analysis.get("groups", {})
        trend_details = groups.get("Trend", {}).get("details", [])
        
        adx_detail = next((d for d in trend_details if d.get("label") == "ADX"), None)
        if adx_detail:
            log(f"✅ ADX Found: {adx_detail['value']} (Status: {adx_detail['text']})")
            
        fan_detail = next((d for d in trend_details if d.get("label") == "FAN"), None)
        if fan_detail:
            log(f"✅ EMA Fan Found: {fan_detail['value']}")
        else:
            log("ℹ️ No EMA Fan detected (Expected if lack of 200 bars)")

        # Verify Squeeze & Divergence
        squeeze = analysis.get("squeeze", {})
        if squeeze.get("is_squeeze"):
            log(f"💎 Squeeze Detected: {squeeze['width']}")
        else:
            log("ℹ️ No Squeeze detected (Volatility not contracted)")
            
        div = analysis.get("divergence", {})
        if div.get("type") != "None":
            log(f"📈 Divergence Detected: {div['type']} ({div.get('severity')})")
        
        # Verify MFI
        vol_details = groups.get("Volume", {}).get("details", [])
        mfi_detail = next((d for d in vol_details if d.get("label") == "MFI"), None)
        if mfi_detail:
            log(f"✅ MFI Found: {mfi_detail['value']}")

        # Verify Specialist Polish Features
        trap = analysis.get("trap", {})
        if trap.get("is_trap"):
            log(f"💎 Trap Detected: {trap.get('level')} Reclaim ({trap.get('strength')})")
        else:
            log("ℹ️ No Trap detected (Price didn't reclaim a major level)")
            
        chase = analysis.get("chase", {})
        if chase.get("is_chasing"):
            log(f"⚠️ Over-extended: {chase.get('dist_atr')} ATR from base")
        else:
            log(f"✅ Entry within buffer: {chase.get('dist_atr')} ATR from base")

        # Verify Risk Levels (ATR based)
        price = df['close'].iloc[-1]
        support = analysis.get("support")
        target = analysis.get("resistance")
        atr = analysis.get("atr")
        
        log(f"\n--- Risk Management (ATR: {atr:.2f}) ---")
        log(f"Current Price: {price:.2f}")
        log(f"Dynamic Support (SL): {support}")
        log(f"Dynamic Target (TP): {target}")
        
        # Calculate Sl / TP distances
        sl_dist_pct = abs(price - support) / price * 100
        tp_dist_pct = abs(target - price) / price * 100
        
        log(f"SL Distance: {sl_dist_pct:.2f}%")
        log(f"TP Distance: {tp_dist_pct:.2f}%")
        
        if sl_dist_pct > 0.1 and tp_dist_pct > 0.1:
            log("✅ Risk levels are dynamic and reasonably spaced.")
        else:
            log("❌ Risk levels might be too tight or static.")

if __name__ == "__main__":
    asyncio.run(test_logic())
