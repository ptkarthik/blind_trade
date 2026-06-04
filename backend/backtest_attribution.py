"""
Factor Attribution Backtester
==============================
Runs the EXACT ta_swing.py analysis logic on 3-5 years of NSE OHLC data,
simulates trade outcomes with faithful exit logic (pullback 2R / breakout hybrid),
records every factor at entry, and measures Expectancy — not just win rate.

Usage:
    python backtest_attribution.py                    # Nifty 50, 3 years
    python backtest_attribution.py --stocks 100       # Nifty 100, 3 years
    python backtest_attribution.py --years 5          # Nifty 50, 5 years
    python backtest_attribution.py --stocks 100 --years 5

Output:
    backtest_results/trades_YYYYMMDD_HHMM.csv         # Every trade with factors + outcome
    Console: Full attribution report with expectancy per factor
"""

import os
import sys
import time
import argparse
import warnings
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# Suppress yfinance noise
warnings.filterwarnings("ignore", category=FutureWarning)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

# --- Path setup so we can import ta_swing ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from app.services.ta_swing import SwingTechnicalAnalysis, safe_scalar

# =====================================================
# STOCK UNIVERSE
# =====================================================
NIFTY_50 = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "BAJFINANCE.NS", "ASIANPAINT.NS", "MARUTI.NS",
    "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "WIPRO.NS", "NESTLEIND.NS",
    "HCLTECH.NS", "TATAMOTORS.NS", "POWERGRID.NS", "NTPC.NS", "M&M.NS",
    "BAJAJFINSV.NS", "ONGC.NS", "TATASTEEL.NS", "ADANIENT.NS", "JSWSTEEL.NS",
    "TECHM.NS", "COALINDIA.NS", "HDFCLIFE.NS", "SBILIFE.NS", "BRITANNIA.NS",
    "GRASIM.NS", "DIVISLAB.NS", "CIPLA.NS", "EICHERMOT.NS", "APOLLOHOSP.NS",
    "DRREDDY.NS", "BPCL.NS", "TATACONSUM.NS", "HINDALCO.NS", "HEROMOTOCO.NS",
    "INDUSINDBK.NS", "SHRIRAMFIN.NS", "BAJAJ-AUTO.NS", "BEL.NS", "TRENT.NS",
]

NIFTY_NEXT_50 = [
    "ADANIPORTS.NS", "BANKBARODA.NS", "CANBK.NS", "DLF.NS", "GODREJCP.NS",
    "HAL.NS", "HAVELLS.NS", "ICICIPRULI.NS", "INDHOTEL.NS", "IOC.NS",
    "IRCTC.NS", "JINDALSTEL.NS", "JUBLFOOD.NS", "LTF.NS", "LTIM.NS",
    "MAXHEALTH.NS", "MOTHERSON.NS", "NAUKRI.NS", "NHPC.NS", "PIDILITIND.NS",
    "PNB.NS", "POLYCAB.NS", "RECLTD.NS", "SIEMENS.NS", "SRF.NS",
    "TORNTPHARM.NS", "TVSMOTOR.NS", "UNIONBANK.NS", "VEDL.NS", "ZOMATO.NS",
    "ABB.NS", "AMBUJACEM.NS", "AUROPHARMA.NS", "BERGEPAINT.NS", "BOSCHLTD.NS",
    "COLPAL.NS", "DABUR.NS", "DIXON.NS", "GAIL.NS", "IRFC.NS",
    "JIOFIN.NS", "LICI.NS", "LUPIN.NS", "MCDOWELL-N.NS", "MAZDOCK.NS",
    "MUTHOOTFIN.NS", "PERSISTENT.NS", "PFC.NS", "SAIL.NS", "ZYDUSLIFE.NS",
]

NIFTY_SYMBOL = "^NSEI"
DATA_DIR = os.path.join(SCRIPT_DIR, "backtest_data")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "backtest_results")

# Backtest parameters
MIN_LOOKBACK = 210          # Min bars before scanning (need 200 for SMA200 + warmup)
TRADE_FORWARD_WINDOW = 30   # Max days to simulate forward


# =====================================================
# DATA LAYER
# =====================================================
def normalize_df(df):
    """
    Normalize yfinance DataFrame to lowercase single-level columns.
    Handles both old and new yfinance output formats.
    """
    df = df.copy()

    # Handle MultiIndex columns (yfinance sometimes returns ('Close', 'RELIANCE.NS'))
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]

    # Ensure DatetimeIndex (required for weekly resampling in compute_context)
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
        else:
            df.index = pd.to_datetime(df.index)

    # Remove timezone info if present (ta library doesn't handle tz-aware)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # Drop any rows with NaN in critical columns
    required = ['open', 'high', 'low', 'close', 'volume']
    for col in required:
        if col not in df.columns:
            return pd.DataFrame()  # Missing critical column
    df = df.dropna(subset=required)

    return df


def download_all_data(symbols, years=3):
    """Download and cache historical OHLC data for all symbols + Nifty."""
    import yfinance as yf

    os.makedirs(DATA_DIR, exist_ok=True)

    end_date = datetime.now()
    # Extra 300 days for SMA200 warmup
    start_date = end_date - timedelta(days=years * 365 + 300)

    data = {}

    # 1. Nifty 50 Index
    nifty_cache = os.path.join(DATA_DIR, "NIFTY50.csv")
    if os.path.exists(nifty_cache):
        nifty_df = pd.read_csv(nifty_cache, index_col=0, parse_dates=True)
        data["NIFTY"] = normalize_df(nifty_df)
        print(f"  [cache] Nifty loaded ({len(data['NIFTY'])} bars)")
    else:
        try:
            nifty_df = yf.download(NIFTY_SYMBOL, start=start_date, end=end_date, progress=False)
            if not nifty_df.empty:
                nifty_df.to_csv(nifty_cache)
                data["NIFTY"] = normalize_df(nifty_df)
                print(f"  [download] Nifty downloaded ({len(data['NIFTY'])} bars)")
        except Exception as e:
            print(f"  [ERROR] Nifty download failed: {e}")

    # 2. Individual stocks
    for i, sym in enumerate(symbols):
        safe_name = sym.replace(".", "_").replace("&", "_")
        cache_path = os.path.join(DATA_DIR, f"{safe_name}.csv")

        if os.path.exists(cache_path):
            try:
                df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
                df = normalize_df(df)
                if len(df) >= MIN_LOOKBACK:
                    data[sym] = df
            except Exception:
                pass  # Re-download on next run
            if (i + 1) % 25 == 0:
                print(f"  [cache] Loaded {i + 1}/{len(symbols)} stocks")
            continue

        try:
            df = yf.download(sym, start=start_date, end=end_date, progress=False)
            if not df.empty:
                df.to_csv(cache_path)
                df = normalize_df(df)
                if len(df) >= MIN_LOOKBACK:
                    data[sym] = df
            time.sleep(0.35)  # Respect rate limits

            if (i + 1) % 10 == 0:
                print(f"  [download] {i + 1}/{len(symbols)} stocks")
        except Exception as e:
            print(f"  [ERROR] {sym}: {e}")

    return data


def compute_nifty_returns(nifty_df):
    """Pre-compute Nifty 20-day returns keyed by date."""
    if nifty_df.empty:
        return {}
    close = nifty_df['close']
    returns = {}
    for i in range(21, len(close)):
        date = close.index[i]
        price_now = float(close.iloc[i])
        price_20d = float(close.iloc[i - 20])
        if price_20d > 0:
            returns[date] = ((price_now / price_20d) - 1) * 100
    return returns


def find_nifty_return(nifty_returns, target_date):
    """Find the closest Nifty return for a given date (handles weekends/holidays)."""
    for offset in range(5):
        d = target_date - timedelta(days=offset)
        if d in nifty_returns:
            return nifty_returns[d]
    return 0.0


# =====================================================
# TRADE SIMULATION
# =====================================================
def simulate_trade(df_future, entry_price, stop_loss, target, strategy):
    """
    Walk-forward trade simulation faithful to trade_manager.py logic.

    Pullback: Strict target at 2R, break-even defense at 1R.
    Breakout: Hybrid — partial 50% at 1.5R, trail remainder via EMA 9.
    Both: Time stop at 7 days (<0.5R), max duration 21 days.
    """
    R = abs(entry_price - stop_loss)
    if R <= 0:
        return {"exit_price": entry_price, "exit_reason": "INVALID_R", "r_multiple": 0.0, "holding_days": 0}

    partial_done = False
    current_sl = stop_loss
    realized_r = 0.0       # R already banked from partial exit
    remaining_pct = 1.0    # 100% of position still open

    for day_idx in range(len(df_future)):
        row = df_future.iloc[day_idx]
        low = safe_scalar(row['low'])
        high = safe_scalar(row['high'])
        close = safe_scalar(row['close'])

        if close <= 0 or low <= 0:
            continue

        # --- Stop Loss (intraday touch) ---
        if low <= current_sl:
            exit_r = (current_sl - entry_price) / R
            total_r = realized_r + (exit_r * remaining_pct)
            return {
                "exit_price": round(current_sl, 2),
                "exit_reason": "STOP_LOSS",
                "r_multiple": round(total_r, 2),
                "holding_days": day_idx + 1,
            }

        # --- PULLBACK: Strict 2R target ---
        if strategy == "PULLBACK":
            if high >= target:
                exit_r = (target - entry_price) / R
                return {
                    "exit_price": round(target, 2),
                    "exit_reason": "TARGET_HIT",
                    "r_multiple": round(exit_r, 2),
                    "holding_days": day_idx + 1,
                }
            # Break-even defense at 1.0R
            if close >= (entry_price + 1.0 * R):
                be_sl = entry_price + (0.1 * R)
                current_sl = max(current_sl, be_sl)

        # --- BREAKOUT: Hybrid trailing exit ---
        elif strategy == "BREAKOUT":
            profit_r = (close - entry_price) / R

            # Phase 1: Break-even defense at 1.0R
            if profit_r >= 1.0 and not partial_done:
                current_sl = max(current_sl, entry_price + 0.1 * R)

            # Phase 2: Partial exit at 1.5R — book 50%
            if profit_r >= 1.5 and not partial_done:
                realized_r = 1.5 * 0.5  # 0.75R banked
                remaining_pct = 0.5
                current_sl = max(current_sl, entry_price + 0.5 * R)
                partial_done = True

            # Phase 3: EMA 9 trailing after partial
            if partial_done and day_idx >= 8:
                ema_9_series = df_future['close'].iloc[:day_idx + 1].ewm(span=9, adjust=False).mean()
                ema_9_val = safe_scalar(ema_9_series.iloc[-1])
                if ema_9_val > current_sl:
                    current_sl = ema_9_val

        # --- Time Stop: 7 days with < 0.5R profit ---
        if day_idx + 1 >= 7:
            current_profit_r = (close - entry_price) / R
            if current_profit_r < 0.5:
                total_r = realized_r + (current_profit_r * remaining_pct)
                return {
                    "exit_price": round(close, 2),
                    "exit_reason": "TIME_STOP_7D",
                    "r_multiple": round(total_r, 2),
                    "holding_days": day_idx + 1,
                }

        # --- Max Duration: 21 days ---
        if day_idx + 1 >= 21:
            current_profit_r = (close - entry_price) / R
            total_r = realized_r + (current_profit_r * remaining_pct)
            return {
                "exit_price": round(close, 2),
                "exit_reason": "MAX_DURATION",
                "r_multiple": round(total_r, 2),
                "holding_days": day_idx + 1,
            }

    # Data ran out before any exit trigger
    if len(df_future) > 0:
        last_close = safe_scalar(df_future.iloc[-1]['close'])
        profit_r = (last_close - entry_price) / R
        total_r = realized_r + (profit_r * remaining_pct)
        return {
            "exit_price": round(last_close, 2),
            "exit_reason": "DATA_END",
            "r_multiple": round(total_r, 2),
            "holding_days": len(df_future),
        }

    return {"exit_price": entry_price, "exit_reason": "NO_DATA", "r_multiple": 0.0, "holding_days": 0}


# =====================================================
# WALK-FORWARD BACKTEST
# =====================================================
def run_backtest(symbols, nifty_returns, data, scan_interval=5):
    """
    Walk-forward backtest: scan every N days, generate signals, simulate trades.
    """
    all_trades = []
    skipped_no_data = 0

    for sym_idx, sym in enumerate(symbols):
        if sym not in data:
            skipped_no_data += 1
            continue

        df = data[sym]
        if len(df) < MIN_LOOKBACK + TRADE_FORWARD_WINDOW:
            continue

        # Track whether we're already in a position for this stock
        position_exit_idx = 0

        scan_points = range(MIN_LOOKBACK, len(df) - TRADE_FORWARD_WINDOW, scan_interval)

        for scan_idx in scan_points:
            # Don't scan if still in a position
            if scan_idx < position_exit_idx:
                continue

            # Slice data up to scan day (inclusive)
            df_slice = df.iloc[:scan_idx + 1].copy()
            scan_date = df.index[scan_idx]
            nifty_ret = find_nifty_return(nifty_returns, scan_date)

            # Run both analyses using EXACT production code
            try:
                ctx = SwingTechnicalAnalysis.compute_context(df_slice)
                pb = SwingTechnicalAnalysis.analyze_pullback(df_slice, nifty_ret, ctx=ctx, earnings_risk=False)
                bo = SwingTechnicalAnalysis.analyze_breakout(df_slice, nifty_ret, ctx=ctx, earnings_risk=False)
            except Exception:
                continue

            # Strategy selection (simplified conflict resolution)
            selected = None
            if pb.get("match") and bo.get("match"):
                selected = bo  # Prefer breakout when both match
            elif bo.get("match"):
                selected = bo
            elif pb.get("match"):
                selected = pb

            if not selected:
                continue

            # --- Extract factor values ---
            entry_price = selected["entry"]
            stop_loss = selected["stop_loss"]
            target_price = selected["target"]
            strategy = selected["strategy"]

            stock_20d_ret = selected.get("stock_20d_return", 0)
            rs_spread = stock_20d_ret - nifty_ret

            # Close position in candle range
            c_h = safe_scalar(df_slice.iloc[-1]['high'])
            c_l = safe_scalar(df_slice.iloc[-1]['low'])
            c_range = c_h - c_l
            close_position = (entry_price - c_l) / c_range if c_range > 0 else 0.5

            # Weekly structure
            weekly_above = True
            if ctx.get('mtf_enabled'):
                w_ema = ctx.get('w_ema_20')
                w_sma = ctx.get('w_sma_50')
                if strategy == "PULLBACK" and w_ema is not None and len(w_ema.dropna()) > 0:
                    weekly_above = entry_price >= safe_scalar(w_ema.dropna().iloc[-1])
                elif strategy == "BREAKOUT" and w_sma is not None and len(w_sma.dropna()) > 0:
                    weekly_above = entry_price >= safe_scalar(w_sma.dropna().iloc[-1])

            # Bounce target (pullback only)
            bounce_target = "N/A"
            if strategy == "PULLBACK":
                reasons_text = str(selected.get("reasons", []))
                bounce_target = "SMA50" if "SMA 50" in reasons_text else "EMA20"

            trade_record = {
                "symbol": sym,
                "scan_date": scan_date.strftime("%Y-%m-%d"),
                "strategy": strategy,
                "setup_type": selected.get("setup_type", ""),
                "entry_price": round(entry_price, 2),
                "stop_loss": round(stop_loss, 2),
                "target": round(target_price, 2),
                "risk_per_share": round(abs(entry_price - stop_loss), 2),
                # --- FACTORS ---
                "conviction": selected.get("conviction", 0),
                "vol_ratio": round(selected.get("vol_ratio", 1.0), 2),
                "vol_3d_avg": round(selected.get("vol_3d_avg", 1.0), 2),
                "vol_5d_avg": round(selected.get("vol_5d_avg", 1.0), 2),
                "rsi": round(selected.get("rsi", 50), 1),
                "adx": round(selected.get("adx", 0), 1),
                "macd_bullish": bool(selected.get("macd_bullish", False)),
                "macd_recovering": bool(selected.get("macd_recovering", False)),
                "macd_expanding": bool(selected.get("macd_expanding", False)),
                "obv_rising": bool(selected.get("obv_rising", False)),
                "rs_spread": round(rs_spread, 2),
                "stock_20d_return": round(stock_20d_ret, 2),
                "close_position": round(close_position, 3),
                "weekly_above": weekly_above,
                "is_squeeze_breakout": bool(selected.get("is_squeeze_breakout", False)),
                "drawdown_pct": round(selected.get("drawdown_pct", 0), 2),
                "bounce_target": bounce_target,
            }

            # --- Simulate trade forward ---
            df_future = df.iloc[scan_idx + 1: scan_idx + 1 + TRADE_FORWARD_WINDOW].copy()
            if len(df_future) < 5:
                continue

            outcome = simulate_trade(df_future, entry_price, stop_loss, target_price, strategy)
            trade_record.update(outcome)
            all_trades.append(trade_record)

            # Block re-entry until this trade exits
            position_exit_idx = scan_idx + 1 + outcome["holding_days"]

        if (sym_idx + 1) % 10 == 0:
            print(f"  [{sym_idx + 1}/{len(symbols)}] {sym:>18} | Trades so far: {len(all_trades)}")

    if skipped_no_data:
        print(f"  [note] {skipped_no_data} symbols skipped (no data)")

    return pd.DataFrame(all_trades)


# =====================================================
# FACTOR ATTRIBUTION ANALYSIS
# =====================================================
def expectancy_stats(subset):
    """Compute expectancy stats for a subset of trades."""
    if subset.empty:
        return {"n": 0}
    wins = subset[subset['r_multiple'] > 0]
    losses = subset[subset['r_multiple'] <= 0]
    n = len(subset)
    wr = len(wins) / n * 100 if n > 0 else 0
    avg_w = wins['r_multiple'].mean() if not wins.empty else 0
    avg_l = losses['r_multiple'].mean() if not losses.empty else 0
    exp = subset['r_multiple'].mean()
    pf = abs(wins['r_multiple'].sum() / losses['r_multiple'].sum()) if not losses.empty and losses['r_multiple'].sum() != 0 else float('inf')
    return {"n": n, "wr": wr, "avg_w": avg_w, "avg_l": avg_l, "exp": exp, "pf": pf}


def factor_attribution(trades_df):
    """Full factor attribution analysis with expectancy."""
    if trades_df.empty:
        print("\n  No trades generated. Check data availability and ta_swing gate thresholds.")
        return None

    print(f"\n{'=' * 90}")
    print(f"  FACTOR ATTRIBUTION REPORT")
    print(f"{'=' * 90}")
    print(f"  Total Trades: {len(trades_df)}")
    print(f"  Date Range: {trades_df['scan_date'].min()} → {trades_df['scan_date'].max()}")

    # --- OVERALL ---
    overall = expectancy_stats(trades_df)
    print(f"\n  OVERALL PERFORMANCE")
    print(f"  {'─' * 60}")
    print(f"  Win Rate:      {overall['wr']:.1f}%")
    print(f"  Avg Winner:    {overall['avg_w']:+.2f}R")
    print(f"  Avg Loser:     {overall['avg_l']:+.2f}R")
    print(f"  Expectancy:    {overall['exp']:+.3f}R per trade")
    print(f"  Profit Factor: {overall['pf']:.2f}")

    # --- BY STRATEGY ---
    print(f"\n  BY STRATEGY")
    print(f"  {'─' * 60}")
    for strat in sorted(trades_df['strategy'].unique()):
        s = expectancy_stats(trades_df[trades_df['strategy'] == strat])
        print(f"  {strat:>12}: {s['n']:>4} trades | Win: {s['wr']:>5.1f}% | "
              f"AvgW: {s['avg_w']:+.2f}R | AvgL: {s['avg_l']:+.2f}R | Exp: {s['exp']:+.3f}R | PF: {s['pf']:.2f}")

    # --- BY EXIT REASON ---
    print(f"\n  BY EXIT REASON")
    print(f"  {'─' * 60}")
    for reason in sorted(trades_df['exit_reason'].unique()):
        sub = trades_df[trades_df['exit_reason'] == reason]
        pct = len(sub) / len(trades_df) * 100
        avg_r = sub['r_multiple'].mean()
        print(f"  {reason:>16}: {len(sub):>4} ({pct:>5.1f}%) | Avg R: {avg_r:+.2f}")

    # --- BINARY FACTORS ---
    print(f"\n{'=' * 90}")
    print(f"  BINARY FACTORS (Present vs Absent)")
    print(f"{'=' * 90}")
    print(f"  {'Factor':<25} {'N(Y)':>5} {'N(N)':>5} {'WR(Y)':>7} {'WR(N)':>7} "
          f"{'Exp(Y)':>8} {'Exp(N)':>8} {'EDGE':>8}  Verdict")
    print(f"  {'─' * 88}")

    binary_factors = [
        ("weekly_above", "Weekly Structure"),
        ("macd_bullish", "MACD Bullish"),
        ("obv_rising", "OBV Rising"),
        ("macd_recovering", "MACD Recovering"),
        ("macd_expanding", "MACD Expanding"),
        ("is_squeeze_breakout", "Squeeze Breakout"),
    ]

    binary_results = []
    for col, label in binary_factors:
        if col not in trades_df.columns:
            continue
        present = trades_df[trades_df[col] == True]
        absent = trades_df[trades_df[col] == False]
        if len(present) < 5 or len(absent) < 5:
            continue

        p = expectancy_stats(present)
        a = expectancy_stats(absent)
        edge = p['exp'] - a['exp']

        verdict = "STRONG" if edge > 0.15 else "USEFUL" if edge > 0.05 else "WEAK" if edge > -0.05 else "HARMFUL"
        binary_results.append((label, p, a, edge, verdict))

        print(f"  {label:<25} {p['n']:>5} {a['n']:>5} {p['wr']:>6.1f}% {a['wr']:>6.1f}% "
              f"{p['exp']:>+7.3f} {a['exp']:>+7.3f} {edge:>+7.3f}  {verdict}")

    # --- CONTINUOUS FACTORS ---
    print(f"\n{'=' * 90}")
    print(f"  CONTINUOUS FACTORS (Binned Expectancy)")
    print(f"{'=' * 90}")

    continuous_factors = [
        ("rs_spread", "Relative Strength (RS Spread)", [
            ("> +10%", lambda x: x > 10),
            ("+5 to +10%", lambda x: (x > 5) & (x <= 10)),
            ("+2 to +5%", lambda x: (x > 2) & (x <= 5)),
            ("0 to +2%", lambda x: (x >= 0) & (x <= 2)),
            ("< 0%", lambda x: x < 0),
        ]),
        ("adx", "ADX Trend Strength", [
            ("> 40", lambda x: x > 40),
            ("35 - 40", lambda x: (x >= 35) & (x <= 40)),
            ("30 - 35", lambda x: (x >= 30) & (x < 35)),
            ("25 - 30", lambda x: (x >= 25) & (x < 30)),
            ("20 - 25", lambda x: (x >= 20) & (x < 25)),
        ]),
        ("vol_ratio", "Volume Ratio (Today)", [
            ("> 4x", lambda x: x > 4.0),
            ("3 - 4x", lambda x: (x > 3.0) & (x <= 4.0)),
            ("2 - 3x", lambda x: (x > 2.0) & (x <= 3.0)),
            ("1.5 - 2x", lambda x: (x > 1.5) & (x <= 2.0)),
            ("1.2 - 1.5x", lambda x: (x > 1.2) & (x <= 1.5)),
        ]),
        ("vol_5d_avg", "Volume Persistence (5d Avg)", [
            ("> 2x", lambda x: x > 2.0),
            ("1.5 - 2x", lambda x: (x > 1.5) & (x <= 2.0)),
            ("1.0 - 1.5x", lambda x: (x > 1.0) & (x <= 1.5)),
            ("< 1x", lambda x: x <= 1.0),
        ]),
        ("close_position", "Close Position (in range)", [
            ("> 0.85", lambda x: x > 0.85),
            ("0.70 - 0.85", lambda x: (x > 0.70) & (x <= 0.85)),
            ("0.60 - 0.70", lambda x: (x > 0.60) & (x <= 0.70)),
            ("< 0.60", lambda x: x <= 0.60),
        ]),
        ("rsi", "RSI at Entry", [
            ("> 70", lambda x: x > 70),
            ("60 - 70", lambda x: (x >= 60) & (x <= 70)),
            ("50 - 60", lambda x: (x >= 50) & (x < 60)),
            ("40 - 50", lambda x: (x >= 40) & (x < 50)),
            ("30 - 40", lambda x: (x >= 30) & (x < 40)),
        ]),
        ("conviction", "Conviction Score", [
            (">= 9", lambda x: x >= 9),
            ("7 - 8", lambda x: (x >= 7) & (x < 9)),
            ("5 - 6", lambda x: (x >= 5) & (x < 7)),
            ("3 - 4", lambda x: (x >= 3) & (x < 5)),
            ("< 3", lambda x: x < 3),
        ]),
    ]

    for col, label, bins in continuous_factors:
        if col not in trades_df.columns:
            continue
        print(f"\n  {label}")
        print(f"  {'─' * 80}")
        print(f"  {'Bin':<16} {'Trades':>6} {'Win%':>7} {'AvgW':>7} {'AvgL':>7} {'Expect':>8} {'PF':>6}")
        print(f"  {'─' * 80}")

        for bin_label, mask_fn in bins:
            mask = mask_fn(trades_df[col])
            sub = trades_df[mask]
            if len(sub) < 3:
                print(f"  {bin_label:<16} {len(sub):>6}   (insufficient data)")
                continue
            s = expectancy_stats(sub)
            print(f"  {bin_label:<16} {s['n']:>6} {s['wr']:>6.1f}% {s['avg_w']:>+6.2f} {s['avg_l']:>+6.2f} "
                  f"{s['exp']:>+7.3f} {s['pf']:>6.2f}")

    # --- PULLBACK: BOUNCE TARGET ---
    pb_trades = trades_df[trades_df['strategy'] == 'PULLBACK']
    if len(pb_trades) >= 10:
        print(f"\n  PULLBACK: Bounce Target (SMA50 vs EMA20)")
        print(f"  {'─' * 60}")
        for bt in ["SMA50", "EMA20"]:
            sub = pb_trades[pb_trades['bounce_target'] == bt]
            if len(sub) >= 3:
                s = expectancy_stats(sub)
                print(f"  {bt:<16} {s['n']:>6} trades | Win: {s['wr']:>5.1f}% | Exp: {s['exp']:>+.3f}R | PF: {s['pf']:.2f}")

    # --- FINAL SUMMARY ---
    print(f"\n{'=' * 90}")
    print(f"  PARETO RANKING: Factors by Absolute Edge")
    print(f"{'=' * 90}")

    # Collect all binary edges
    all_edges = []
    for label, p, a, edge, verdict in binary_results:
        all_edges.append({"Factor": label, "Type": "Binary", "Edge": edge, "Verdict": verdict, "Trades": p['n']})

    # Add continuous factor ranges with highest/lowest expectancy
    for col, label, bins in continuous_factors:
        if col not in trades_df.columns:
            continue
        best_exp = -999
        best_bin = ""
        for bin_label, mask_fn in bins:
            sub = trades_df[mask_fn(trades_df[col])]
            if len(sub) >= 5:
                exp = sub['r_multiple'].mean()
                if exp > best_exp:
                    best_exp = exp
                    best_bin = bin_label
        if best_exp > -999:
            all_edges.append({
                "Factor": f"{label} [{best_bin}]",
                "Type": "Continuous",
                "Edge": best_exp,
                "Verdict": "BEST_BIN",
                "Trades": len(trades_df[mask_fn(trades_df[col])])
            })

    edges_df = pd.DataFrame(all_edges).sort_values("Edge", ascending=False)
    print(f"\n  {'Rank':<5} {'Factor':<40} {'Edge':>8}  {'Trades':>6}  Verdict")
    print(f"  {'─' * 75}")
    for rank, (_, row) in enumerate(edges_df.iterrows(), 1):
        print(f"  {rank:<5} {row['Factor']:<40} {row['Edge']:>+7.3f}  {row['Trades']:>6}  {row['Verdict']}")

    return edges_df


# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Factor Attribution Backtester for Swing Trading")
    parser.add_argument("--stocks", type=int, default=50, choices=[50, 100],
                        help="Stock universe: 50 (Nifty 50) or 100 (Nifty 100)")
    parser.add_argument("--years", type=int, default=3, help="Years of historical data (2-5)")
    parser.add_argument("--interval", type=int, default=5, help="Scan every N trading days")
    args = parser.parse_args()

    symbols = NIFTY_50 if args.stocks <= 50 else NIFTY_50 + NIFTY_NEXT_50

    print(f"\n{'=' * 90}")
    print(f"  BLIND TRADE — FACTOR ATTRIBUTION BACKTESTER")
    print(f"{'=' * 90}")
    print(f"  Universe:       {len(symbols)} stocks ({'Nifty 50' if args.stocks <= 50 else 'Nifty 100'})")
    print(f"  History:        {args.years} years")
    print(f"  Scan Interval:  Every {args.interval} trading days")
    print(f"  Trade Sim:      Pullback (strict 2R) + Breakout (hybrid 1.5R partial + EMA9 trail)")
    print(f"  Time Stops:     7-day sideways (<0.5R) + 21-day max duration")
    print(f"")

    # Phase 1: Data
    print(f"[1/4] Downloading historical data...")
    data = download_all_data(symbols, years=args.years)
    print(f"  Total: {len(data) - 1} stocks + Nifty loaded\n")

    # Phase 2: Nifty Returns
    print(f"[2/4] Computing Nifty 20-day returns...")
    nifty_df = data.get("NIFTY", pd.DataFrame())
    nifty_returns = compute_nifty_returns(nifty_df)
    print(f"  {len(nifty_returns)} daily Nifty return data points\n")

    # Phase 3: Backtest
    print(f"[3/4] Running walk-forward backtest...")
    t_start = time.time()
    trades_df = run_backtest(symbols, nifty_returns, data, scan_interval=args.interval)
    elapsed = time.time() - t_start
    print(f"\n  Backtest complete: {len(trades_df)} trades generated in {elapsed:.1f}s\n")

    # Save raw trade data
    os.makedirs(RESULTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    trades_path = os.path.join(RESULTS_DIR, f"trades_{timestamp}.csv")
    if not trades_df.empty:
        trades_df.to_csv(trades_path, index=False)
        print(f"  Trades saved to: {trades_path}")

    # Phase 4: Attribution
    print(f"\n[4/4] Running factor attribution analysis...")
    edges_df = factor_attribution(trades_df)

    # Save edges summary
    if edges_df is not None and not edges_df.empty:
        edges_path = os.path.join(RESULTS_DIR, f"factor_edges_{timestamp}.csv")
        edges_df.to_csv(edges_path, index=False)
        print(f"\n  Factor rankings saved to: {edges_path}")

    print(f"\n{'=' * 90}")
    print(f"  BACKTEST COMPLETE")
    print(f"{'=' * 90}\n")
