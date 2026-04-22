"""
Institutional Swing Engine V3 Backtester
Uses jugaad-data (NSE India direct) to bypass Yahoo Finance rate limits.
Simulates exact V3 ta_swing strategy rules on historical data.
"""

import argparse
import pandas as pd
import numpy as np
import time
import sys
import os
from datetime import datetime, timedelta, date

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.ta_swing import ta_swing, safe_scalar


def fetch_nse_data(symbol_clean, from_date, to_date):
    """Fetch daily OHLCV from NSE India via jugaad-data."""
    from jugaad_data.nse import stock_df
    try:
        df = stock_df(symbol=symbol_clean, from_date=from_date, to_date=to_date, series="EQ")
        if df is not None and not df.empty:
            df = df.rename(columns={
                "DATE": "date",
                "OPEN": "open",
                "HIGH": "high",
                "LOW": "low",
                "CLOSE": "close",
                "VOLUME": "volume",
                "NO OF TRADES": "trades"
            })
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            df = df.sort_index()
            # Keep only needed columns
            df = df[['open', 'high', 'low', 'close', 'volume']]
            return df
    except Exception as e:
        print(f"  Error fetching {symbol_clean}: {e}")
    return pd.DataFrame()


def fetch_nifty_data(from_date, to_date):
    """Fetch Nifty proxy data using NIFTYBEES ETF from NSE."""
    from jugaad_data.nse import stock_df
    try:
        df = stock_df(symbol="NIFTYBEES", from_date=from_date, to_date=to_date, series="EQ")
        if df is not None and not df.empty:
            df = df.rename(columns={
                "DATE": "date",
                "OPEN": "open",
                "HIGH": "high",
                "LOW": "low",
                "CLOSE": "close",
                "VOLUME": "volume",
            })
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            df = df.sort_index()
            df = df[['open', 'high', 'low', 'close', 'volume']]
            return df
    except Exception as e:
        print(f"  Error fetching NIFTYBEES (Nifty proxy): {e}")
    return pd.DataFrame()


def simulate_trade(active_trade, latest_row, ctx, i):
    """Simulate one day of trade management."""
    high = safe_scalar(latest_row['high'])
    low = safe_scalar(latest_row['low'])
    close = safe_scalar(latest_row['close'])
    open_p = safe_scalar(latest_row['open'])

    active_trade['days_held'] += 1

    if open_p < active_trade['sl']:
        active_trade['exit_price'] = open_p
        active_trade['exit_reason'] = "GAP_DOWN_SL"
        active_trade['status'] = "CLOSED"
    elif low <= active_trade['sl']:
        active_trade['exit_price'] = active_trade['sl']
        active_trade['exit_reason'] = "STOP_LOSS"
        active_trade['status'] = "CLOSED"
    elif high >= active_trade['target'] and active_trade['strategy'] == 'PULLBACK':
        active_trade['exit_price'] = active_trade['target']
        active_trade['exit_reason'] = "TARGET_HIT"
        active_trade['status'] = "CLOSED"
    elif high >= active_trade['target'] and active_trade['strategy'] == 'BREAKOUT' and not active_trade['partial_taken']:
        active_trade['partial_taken'] = True
        active_trade['partial_price'] = active_trade['target']
        active_trade['sl'] = active_trade['entry']

    if active_trade['status'] == "OPEN" and active_trade['days_held'] >= 7:
        current_r = (close - active_trade['entry']) / max(active_trade['risk'], 0.01)
        if current_r < 0.5:
            active_trade['exit_price'] = close
            active_trade['exit_reason'] = "TIME_DECAY_7D"
            active_trade['status'] = "CLOSED"

    if active_trade['status'] == "OPEN" and active_trade['days_held'] >= 21:
        active_trade['exit_price'] = close
        active_trade['exit_reason'] = "MAX_TIME_21D"
        active_trade['status'] = "CLOSED"

    if active_trade['status'] == "OPEN" and active_trade['partial_taken']:
        try:
            ema9 = safe_scalar(ctx['ema_9'].iloc[i])
            if close < ema9:
                active_trade['exit_price'] = close
                active_trade['exit_reason'] = "EMA9_TRAIL_HIT"
                active_trade['status'] = "CLOSED"
        except (IndexError, KeyError):
            pass

    if active_trade['status'] == "CLOSED":
        risk = max(active_trade['risk'], 0.01)
        if active_trade['partial_taken']:
            r1 = (active_trade['partial_price'] - active_trade['entry']) / risk
            r2 = (active_trade['exit_price'] - active_trade['entry']) / risk
            active_trade['r_multiple'] = (r1 + r2) / 2
        else:
            active_trade['r_multiple'] = (active_trade['exit_price'] - active_trade['entry']) / risk

    return active_trade


def run_backtest(symbols, years=2):
    to_date = date.today()
    from_date = to_date - timedelta(days=years * 365)

    print(f"\n{'='*60}")
    print(f"  SWING ENGINE V3 BACKTESTER (NSE Direct)")
    print(f"  Symbols: {', '.join(symbols)}")
    print(f"  Period : {from_date} to {to_date}")
    print(f"{'='*60}\n")

    print("Phase 1: Fetching NIFTY 50 baseline from NSE...")
    nifty_df = fetch_nifty_data(from_date, to_date)
    if nifty_df.empty or len(nifty_df) < 50:
        print("FATAL: Nifty data insufficient. Aborting.")
        return
    print(f"  Nifty data: {len(nifty_df)} days OK")

    # Pre-compute Nifty 20D returns
    nifty_returns = {}
    for idx_pos in range(21, len(nifty_df)):
        dt = nifty_df.index[idx_pos]
        p_current = safe_scalar(nifty_df.iloc[idx_pos]['close'])
        p_20d = safe_scalar(nifty_df.iloc[idx_pos - 20]['close'])
        if p_20d > 0:
            key = dt.date() if hasattr(dt, 'date') else dt
            nifty_returns[key] = ((p_current / p_20d) - 1) * 100

    all_trades = []

    print("\nPhase 2: Running strategy simulation...\n")

    for sym in symbols:
        print(f"--- {sym} ---")
        df = fetch_nse_data(sym, from_date, to_date)
        time.sleep(1.5)  # Rate limit courtesy to NSE
        
        if df.empty or len(df) < 200:
            print(f"  SKIP: {len(df)} days (need 200+)")
            continue

        print(f"  Data: {len(df)} days | Computing indicators...")
        ctx = ta_swing.compute_context(df)

        active_trade = None
        signals_found = 0

        for i in range(200, len(df) - 1):
            dt = df.index[i]
            date_key = dt.date() if hasattr(dt, 'date') else dt
            latest_row = df.iloc[i]

            if active_trade:
                active_trade = simulate_trade(active_trade, latest_row, ctx, i)
                if active_trade['status'] == "CLOSED":
                    all_trades.append(active_trade)
                    active_trade = None
                continue

            df_slice = df.iloc[:i + 1]
            ctx_slice = {k: (v.iloc[:i + 1] if isinstance(v, pd.Series) else v) for k, v in ctx.items()}
            nifty_ret = nifty_returns.get(date_key, 0)

            try:
                pb = ta_swing.analyze_pullback(df_slice, nifty_ret, ctx_slice)
            except Exception:
                pb = {"match": False}
            try:
                bo = ta_swing.analyze_breakout(df_slice, nifty_ret, ctx_slice)
            except Exception:
                bo = {"match": False}

            selected = None
            if pb.get('match') and bo.get('match'):
                selected = bo
            elif bo.get('match'):
                selected = bo
            elif pb.get('match'):
                selected = pb

            if selected:
                # Minimum viable conviction check
                if selected.get('conviction', 0) < 5:
                    continue
                    
                tomorrow_open = safe_scalar(df.iloc[i + 1]['open'])
                if tomorrow_open > selected['entry'] * 1.02:
                    continue
                risk = tomorrow_open - selected['stop_loss']
                if risk <= 0:
                    continue

                signals_found += 1
                active_trade = {
                    'symbol': sym,
                    'entry_date': str(df.index[i + 1].date() if hasattr(df.index[i + 1], 'date') else df.index[i + 1]),
                    'entry': tomorrow_open,
                    'sl': selected['stop_loss'],
                    'target': selected['target'],
                    'risk': risk,
                    'strategy': selected['strategy'],
                    'conviction': selected.get('conviction', 0),
                    'status': 'OPEN',
                    'days_held': 0,
                    'partial_taken': False,
                    'partial_price': 0.0,
                    'exit_price': 0.0,
                    'exit_reason': '',
                    'r_multiple': 0.0
                }

        closed_for_sym = len([t for t in all_trades if t['symbol'] == sym])
        print(f"  Signals: {signals_found} | Trades closed: {closed_for_sym}")

    # =================================================================
    # Phase 3: INSTITUTIONAL REPORT
    # =================================================================
    print(f"\n{'='*60}")
    print(f"  INSTITUTIONAL BACKTEST REPORT V3")
    print(f"{'='*60}")

    if not all_trades:
        print("  No trades triggered in this period.")
        return

    total = len(all_trades)
    winners = [t for t in all_trades if t['r_multiple'] > 0]
    losers = [t for t in all_trades if t['r_multiple'] <= 0]

    win_rate = len(winners) / total * 100
    avg_r = sum(t['r_multiple'] for t in all_trades) / total
    avg_win_r = sum(t['r_multiple'] for t in winners) / max(len(winners), 1)
    avg_loss_r = sum(t['r_multiple'] for t in losers) / max(len(losers), 1)
    avg_days = sum(t['days_held'] for t in all_trades) / total

    gross_profit = sum(t['r_multiple'] for t in winners) if winners else 0
    gross_loss = abs(sum(t['r_multiple'] for t in losers)) if losers else 0.01
    profit_factor = gross_profit / max(gross_loss, 0.01)

    cumulative_r = []
    running = 0
    for t in all_trades:
        running += t['r_multiple']
        cumulative_r.append(running)
    peak = cumulative_r[0]
    max_dd = 0
    for val in cumulative_r:
        if val > peak:
            peak = val
        dd = peak - val
        if dd > max_dd:
            max_dd = dd

    exit_reasons = {}
    for t in all_trades:
        reason = t.get('exit_reason', 'UNKNOWN')
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

    print(f"\n  Total Trades    : {total}")
    print(f"  Winners         : {len(winners)}")
    print(f"  Losers          : {len(losers)}")
    print(f"  Win Rate        : {win_rate:.1f}%")
    print(f"  Avg R-Multiple  : {avg_r:.2f}R")
    print(f"  Avg Winner      : {avg_win_r:.2f}R")
    print(f"  Avg Loser       : {avg_loss_r:.2f}R")
    print(f"  Profit Factor   : {profit_factor:.2f}")
    print(f"  Max Drawdown    : {max_dd:.2f}R")
    print(f"  Avg Hold Days   : {avg_days:.1f}")

    print(f"\n  --- EXPECTANCY ---")
    print(f"  {avg_r:.2f}R per trade")
    if avg_r >= 0.5:
        print(f"  VERDICT: EXCELLENT (>=0.5R)")
    elif avg_r >= 0.2:
        print(f"  VERDICT: GOOD (>=0.2R)")
    elif avg_r > 0:
        print(f"  VERDICT: MARGINAL (>0R but <0.2R) - Needs tuning")
    else:
        print(f"  VERDICT: UNPROFITABLE - Requires filter/scoring overhaul")

    print(f"\n  --- BY STRATEGY ---")
    bo_trades = [t for t in all_trades if t['strategy'] == 'BREAKOUT']
    pb_trades = [t for t in all_trades if t['strategy'] == 'PULLBACK']

    if bo_trades:
        bo_wr = len([t for t in bo_trades if t['r_multiple'] > 0]) / len(bo_trades) * 100
        bo_avg_r = sum(t['r_multiple'] for t in bo_trades) / len(bo_trades)
        print(f"  BREAKOUT : {len(bo_trades)} trades | {bo_wr:.1f}% WR | {bo_avg_r:.2f}R avg")
    else:
        print(f"  BREAKOUT : 0 trades")

    if pb_trades:
        pb_wr = len([t for t in pb_trades if t['r_multiple'] > 0]) / len(pb_trades) * 100
        pb_avg_r = sum(t['r_multiple'] for t in pb_trades) / len(pb_trades)
        print(f"  PULLBACK : {len(pb_trades)} trades | {pb_wr:.1f}% WR | {pb_avg_r:.2f}R avg")
    else:
        print(f"  PULLBACK : 0 trades")

    print(f"\n  --- EXIT REASONS ---")
    for reason, count in sorted(exit_reasons.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        print(f"  {reason:20s}: {count:3d} ({pct:.1f}%)")

    print(f"\n  --- CONVICTION ANALYSIS ---")
    high_conv = [t for t in all_trades if t['conviction'] >= 7]
    low_conv = [t for t in all_trades if t['conviction'] < 7]

    if high_conv:
        hc_wr = len([t for t in high_conv if t['r_multiple'] > 0]) / len(high_conv) * 100
        hc_avg = sum(t['r_multiple'] for t in high_conv) / len(high_conv)
        print(f"  High (>=7) : {len(high_conv)} trades | {hc_wr:.1f}% WR | {hc_avg:.2f}R avg")

    if low_conv:
        lc_wr = len([t for t in low_conv if t['r_multiple'] > 0]) / len(low_conv) * 100
        lc_avg = sum(t['r_multiple'] for t in low_conv) / len(low_conv)
        print(f"  Low  (<7)  : {len(low_conv)} trades | {lc_wr:.1f}% WR | {lc_avg:.2f}R avg")

    print(f"\n  --- TRADE LOG (Last 20) ---")
    print(f"  {'Date':12s} {'Symbol':15s} {'Strat':10s} {'Entry':>8s} {'Exit':>8s} {'R':>6s} {'Days':>5s} {'Reason':20s}")
    print(f"  {'-'*86}")
    for t in all_trades[-20:]:
        icon = "+" if t['r_multiple'] > 0 else "-"
        print(f"  {t['entry_date']:12s} {t['symbol']:15s} {t['strategy']:10s} {t['entry']:8.1f} {t['exit_price']:8.1f} {icon}{abs(t['r_multiple']):5.2f}R {t['days_held']:5d} {t['exit_reason']:20s}")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser("Swing Backtester V3 (NSE Direct)")
    parser.add_argument("--symbols", type=str,
                        default="RELIANCE,TCS,HDFCBANK,INFY,ICICIBANK,SBIN,BHARTIARTL,ITC,KOTAKBANK,LT",
                        help="Comma-separated NSE symbols (without .NS suffix)")
    parser.add_argument("--years", type=int, default=2, help="Years of historical data (1, 2, 3)")
    args = parser.parse_args()

    symbol_list = [s.strip() for s in args.symbols.split(",")]
    run_backtest(symbol_list, args.years)
