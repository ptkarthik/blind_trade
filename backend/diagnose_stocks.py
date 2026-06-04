"""
Diagnostic: Compare ACMESOLAR.NS (Score 62) vs INFOBEAN.NS (Score 49)
Why is the HOLD up +3.45% and the BUY flat?
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
import asyncio

from app.services.ta_swing import SwingTechnicalAnalysis, safe_scalar

async def diagnose_stock(sym):
    """Fetch data and run full analysis for a single stock."""
    print(f"\n{'='*80}")
    print(f"  DIAGNOSING: {sym}")
    print(f"{'='*80}")
    
    # Try Kite first, then Yahoo
    df = pd.DataFrame()
    source = "NONE"
    
    try:
        from app.services.kite_data import kite_data
        await kite_data.initialize()
        if kite_data.is_ready:
            df = await kite_data.fetch_ohlc(sym, period="1y", interval="1d")
            if not df.empty:
                source = "KITE"
    except Exception as e:
        print(f"  Kite failed: {e}")
    
    if df.empty:
        try:
            import yfinance as yf
            raw = yf.download(sym, period="1y", interval="1d", progress=False)
            if not raw.empty:
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = [c[0].lower() for c in raw.columns]
                else:
                    raw.columns = [c.lower() for c in raw.columns]
                if raw.index.tz is not None:
                    raw.index = raw.index.tz_localize(None)
                df = raw.dropna(subset=['open','high','low','close','volume'])
                source = "YAHOO"
        except Exception as e:
            print(f"  Yahoo failed: {e}")
    
    if df.empty:
        print(f"  ERROR: No data available for {sym}")
        return None
    
    print(f"  Data: {len(df)} bars from {source} ({df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')})")
    
    # Get Nifty 20d return
    nifty_ret = 0.0
    try:
        if source == "KITE" and kite_data.is_ready:
            nifty_df = await kite_data.fetch_ohlc("^NSEI", period="2mo", interval="1d")
        else:
            import yfinance as yf
            nifty_raw = yf.download("^NSEI", period="2mo", interval="1d", progress=False)
            nifty_df = nifty_raw
            if isinstance(nifty_df.columns, pd.MultiIndex):
                nifty_df.columns = [c[0].lower() for c in nifty_df.columns]
            else:
                nifty_df.columns = [c.lower() for c in nifty_df.columns]
        
        if not nifty_df.empty and len(nifty_df) >= 21:
            nc = nifty_df['close']
            nifty_ret = ((float(nc.iloc[-1]) / float(nc.iloc[-21])) - 1) * 100
            print(f"  Nifty 20d Return: {nifty_ret:.2f}%")
    except Exception as e:
        print(f"  Nifty fetch failed (using 0%): {e}")
    
    # Run both analyses
    try:
        ctx = SwingTechnicalAnalysis.compute_context(df)
    except Exception as e:
        print(f"  compute_context ERROR: {e}")
        return None
    
    # --- PULLBACK ---
    print(f"\n  --- PULLBACK ANALYSIS ---")
    pb = SwingTechnicalAnalysis.analyze_pullback(df, nifty_ret, ctx=ctx, earnings_risk=False)
    if pb.get("match"):
        print(f"  MATCH: YES")
        print(f"  Strategy: {pb['strategy']}, Setup: {pb.get('setup_type')}")
        print(f"  Entry: {pb['entry']}, SL: {pb['stop_loss']}, Target: {pb['target']}")
        print(f"  Conviction: {pb['conviction']}")
        print(f"  RSI: {pb['rsi']}, ADX: {pb['adx']}, Vol: {pb['vol_ratio']:.1f}x")
        print(f"  Vol 3d: {pb.get('vol_3d_avg', 'N/A')}, Vol 5d: {pb.get('vol_5d_avg', 'N/A')}")
        print(f"  MACD Bull: {pb.get('macd_bullish')}, MACD Recov: {pb.get('macd_recovering')}")
        print(f"  OBV Rising: {pb.get('obv_rising')}")
        print(f"  Stock 20d Ret: {pb.get('stock_20d_return')}%, RS Spread: {pb.get('stock_20d_return',0) - nifty_ret:.1f}%")
        print(f"  Drawdown: {pb.get('drawdown_pct')}%")
        for r in pb.get('reasons', []):
            print(f"    - {r.get('label','')}: {r.get('text','')} ({r.get('type','')})")
    else:
        print(f"  MATCH: NO — {pb.get('reason', 'Unknown')}")
    
    # --- BREAKOUT ---
    print(f"\n  --- BREAKOUT ANALYSIS ---")
    bo = SwingTechnicalAnalysis.analyze_breakout(df, nifty_ret, ctx=ctx, earnings_risk=False)
    if bo.get("match"):
        print(f"  MATCH: YES")
        print(f"  Strategy: {bo['strategy']}, Setup: {bo.get('setup_type')}")
        print(f"  Entry: {bo['entry']}, SL: {bo['stop_loss']}, Target: {bo['target']}")
        print(f"  Conviction: {bo['conviction']}")
        print(f"  RSI: {bo['rsi']}, ADX: {bo['adx']}, Vol: {bo['vol_ratio']:.1f}x")
        print(f"  Vol 3d: {bo.get('vol_3d_avg', 'N/A')}, Vol 5d: {bo.get('vol_5d_avg', 'N/A')}")
        print(f"  MACD Bull: {bo.get('macd_bullish')}, MACD Expand: {bo.get('macd_expanding')}")
        print(f"  OBV Rising: {bo.get('obv_rising')}")
        print(f"  Stock 20d Ret: {bo.get('stock_20d_return')}%, RS Spread: {bo.get('stock_20d_return',0) - nifty_ret:.1f}%")
        print(f"  Squeeze Breakout: {bo.get('is_squeeze_breakout')}")
        for r in bo.get('reasons', []):
            print(f"    - {r.get('label','')}: {r.get('text','')} ({r.get('type','')})")
    else:
        print(f"  MATCH: NO — {bo.get('reason', 'Unknown')}")
    
    # --- SCORE SIMULATION ---
    selected = None
    if pb.get("match") and bo.get("match"):
        selected = bo  # Prefer breakout
    elif bo.get("match"):
        selected = bo
    elif pb.get("match"):
        selected = pb
    
    if not selected:
        print(f"\n  NO STRATEGY MATCHED — cannot score")
        return {"symbol": sym, "matched": False, "pb_reason": pb.get("reason"), "bo_reason": bo.get("reason")}
    
    print(f"\n  --- SCORING SIMULATION (100-pt scale) ---")
    print(f"  Selected Strategy: {selected['strategy']}")
    
    score = 0
    
    # C1: Conviction
    conviction = selected.get("conviction", 0)
    max_conv = 12 if selected["strategy"] == "BREAKOUT" else 10
    conv_score = round((conviction / max(max_conv, 1)) * 25)
    score += conv_score
    print(f"  C1 Conviction:    +{conv_score:>2} ({conviction}/{max_conv} × 25)")
    
    # C2: Volume Quality
    vol_ratio = selected.get("vol_ratio", 1.0)
    if vol_ratio > 4.0: vol_score = 15
    elif vol_ratio > 3.0: vol_score = 13
    elif vol_ratio > 2.5: vol_score = 11
    elif vol_ratio > 2.0: vol_score = 9
    elif vol_ratio > 1.5: vol_score = 6
    elif vol_ratio > 1.2: vol_score = 3
    else: vol_score = 0
    score += vol_score
    print(f"  C2 Volume:        +{vol_score:>2} ({vol_ratio:.1f}x)")
    
    # C2.5: Volume Persistence
    vol_3d = selected.get("vol_3d_avg", 1.0)
    vol_5d = selected.get("vol_5d_avg", 1.0)
    vol_persist_raw = 0
    if vol_5d > 2.0: vol_persist_raw = 5
    elif vol_5d > 1.5: vol_persist_raw = 3
    elif vol_3d > 1.5: vol_persist_raw = 2
    vol_persist = min(vol_persist_raw, 15 - vol_score)
    vol_persist = max(0, vol_persist)
    score += vol_persist
    print(f"  C2.5 Persistence: +{vol_persist:>2} (3d:{vol_3d:.1f}x, 5d:{vol_5d:.1f}x, raw:{vol_persist_raw}, cap:{15 - vol_score})")
    
    # C3: Relative Strength
    stock_ret = selected.get("stock_20d_return", 0)
    rs_spread = stock_ret - nifty_ret
    if rs_spread > 10: rs_score = 10
    elif rs_spread > 5: rs_score = 7
    elif rs_spread > 2: rs_score = 4
    else: rs_score = 1
    score += rs_score
    print(f"  C3 RS:            +{rs_score:>2} (spread: {rs_spread:+.1f}%)")
    
    # C4: Market Context (simplified - no live market data)
    print(f"  C4 Market:        (requires live market context - skipping)")
    
    # C5: ADX
    adx_val = selected.get("adx", 0)
    adx_penalty = 0
    if adx_val >= 50: adx_score = 0; adx_penalty = 5
    elif adx_val >= 40: adx_score = 5
    elif adx_val >= 35: adx_score = 10
    elif adx_val >= 30: adx_score = 7
    elif adx_val >= 25: adx_score = 4
    else: adx_score = 0
    score += adx_score - adx_penalty
    print(f"  C5 ADX:           +{adx_score:>2} - {adx_penalty} penalty (ADX={adx_val:.1f})")
    
    # C6: Strategy Bonus
    strat_bonus = 0
    if selected["strategy"] == "PULLBACK":
        reasons_text = str(selected.get("reasons", []))
        if "SMA 50" in reasons_text:
            strat_bonus = 10
            print(f"  C6 Strat Bonus:   +10 (SMA50 bounce)")
        else:
            strat_bonus = 5
            print(f"  C6 Strat Bonus:   + 5 (EMA20 bounce)")
        if selected.get("setup_type") == "REVERSAL_PULLBACK":
            strat_bonus += 5
            print(f"  C6 Reversal:      + 5")
    elif selected["strategy"] == "BREAKOUT":
        strat_bonus = 3
        if selected.get("is_squeeze_breakout"):
            strat_bonus += 10
            print(f"  C6 Strat Bonus:   +13 (Squeeze + Base)")
        else:
            print(f"  C6 Strat Bonus:   + 3 (Standard BO)")
    strat_bonus = min(15, strat_bonus)
    score += strat_bonus
    
    # C7: Institutional
    inst_score = 0
    if selected.get("macd_bullish"): inst_score += 3
    if selected.get("macd_expanding") or selected.get("macd_recovering"): inst_score += 3
    if selected.get("obv_rising"): inst_score += 4
    score += inst_score
    print(f"  C7 Institutional: +{inst_score:>2} (MACD:{selected.get('macd_bullish')}, Expand/Recov:{selected.get('macd_expanding') or selected.get('macd_recovering')}, OBV:{selected.get('obv_rising')})")
    
    # V2 Penalties (simplified - check extension)
    latest_close = safe_scalar(df.iloc[-1]['close'])
    if len(df) >= 60:
        low_60d = safe_scalar(df['low'].iloc[-60:].min())
    else:
        low_60d = safe_scalar(df['low'].min())
    
    extension = latest_close / low_60d if low_60d > 0 else 1.0
    ext_pen = 0
    if extension > 2.0: ext_pen = 25
    elif extension > 1.5: ext_pen = 15
    score -= ext_pen
    print(f"  V2 Extension:     -{ext_pen:>2} ({(extension-1)*100:.0f}% above 60d low)")
    
    # Chasing
    if len(df) >= 6:
        price_5d = safe_scalar(df['close'].iloc[-6])
        roc_5d = ((latest_close - price_5d) / price_5d) * 100 if price_5d > 0 else 0
        chase_thresh = 20 if selected["strategy"] == "BREAKOUT" else 15
        chase_pen = 10 if roc_5d > chase_thresh else 0
        score -= chase_pen
        print(f"  V2 Chasing:       -{chase_pen:>2} (5d ROC: {roc_5d:+.1f}%, thresh: {chase_thresh}%)")
    
    # Distribution
    is_red = safe_scalar(df.iloc[-1]['close']) < safe_scalar(df.iloc[-1]['open'])
    dist_pen = 5 if (extension > 1.3 and vol_ratio > 3.0 and is_red) else 0
    score -= dist_pen
    print(f"  V2 Distribution:  -{dist_pen:>2} (ext:{extension:.1f}, vol:{vol_ratio:.1f}x, red:{is_red})")
    
    final = round(min(100, max(0, score)), 1)
    print(f"\n  {'─'*40}")
    print(f"  ESTIMATED SCORE:  {final} (without market context penalties)")
    print(f"  {'─'*40}")
    
    return {
        "symbol": sym,
        "matched": True,
        "strategy": selected["strategy"],
        "conviction": conviction,
        "vol_ratio": vol_ratio,
        "vol_3d": vol_3d,
        "vol_5d": vol_5d,
        "rsi": selected.get("rsi"),
        "adx": adx_val,
        "rs_spread": rs_spread,
        "macd_bullish": selected.get("macd_bullish"),
        "obv_rising": selected.get("obv_rising"),
        "score_estimate": final,
    }

async def main():
    print("DIAGNOSTIC: ACMESOLAR.NS (Score 62, BUY) vs INFOBEAN.NS (Score 49, HOLD)")
    print("Why is the HOLD up +3.45% and the BUY flat?")
    
    r1 = await diagnose_stock("ACMESOLAR.NS")
    r2 = await diagnose_stock("INFOBEAN.NS")
    
    if r1 and r2 and r1.get("matched") and r2.get("matched"):
        print(f"\n{'='*80}")
        print(f"  COMPARISON SUMMARY")
        print(f"{'='*80}")
        print(f"  {'Metric':<25} {'ACMESOLAR':>15} {'INFOBEAN':>15} {'Gap':>10}")
        print(f"  {'─'*65}")
        for k in ["strategy", "conviction", "vol_ratio", "vol_3d", "vol_5d", 
                   "rsi", "adx", "rs_spread", "macd_bullish", "obv_rising", "score_estimate"]:
            v1 = r1.get(k, "N/A")
            v2 = r2.get(k, "N/A")
            gap = ""
            if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                gap = f"{v1 - v2:+.1f}"
            print(f"  {k:<25} {str(v1):>15} {str(v2):>15} {gap:>10}")

if __name__ == "__main__":
    asyncio.run(main())
