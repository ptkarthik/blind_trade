import pandas as pd
import numpy as np

def test_v34_accumulation_logic():
    print("Starting Stand-alone V3.4 Accumulation Logic Verification...")
    
    def mock_vwap(df):
        tp = (df['high'] + df['low'] + df['close']) / 3
        return (tp * df['volume']).cumsum() / df['volume'].cumsum()

    def get_acc_status(df):
        try:
            latest = df.iloc[-1]
            last_20 = df.tail(20)
            highest_high = last_20['high'].max()
            lowest_low = last_20['low'].min()
            current_price = latest['close']
            
            range_pct = (highest_high - lowest_low) / current_price * 100
            
            vwap_series = mock_vwap(df)
            vwap_now = vwap_series.iloc[-1]
            price_near_vwap = current_price >= vwap_now * 0.995 
            consolidation_zone = (range_pct < 2.5) and price_near_vwap

            avg_vol_last_10 = last_20['volume'].tail(10).mean()
            avg_vol_prev_10 = last_20['volume'].iloc[0:10].mean()
            volume_acc_ratio = avg_vol_last_10 / avg_vol_prev_10 if avg_vol_prev_10 > 0 else 1.0
            volume_accumulation = volume_acc_ratio > 1.25

            pullbacks_shallow = True
            for i in range(-5, 0):
                pb = (highest_high - df.iloc[i]['low']) / highest_high * 100
                if pb > 2.0:
                    pullbacks_shallow = False
                    break
            higher_lows = latest['low'] > df['low'].iloc[-10]
            higher_lows_pattern = pullbacks_shallow and higher_lows

            touches = 0
            for i in range(-20, 0):
                if df.iloc[i]['low'] <= vwap_series.iloc[i] * 1.002 and df.iloc[i]['close'] > vwap_series.iloc[i]:
                    touches += 1
            vwap_accumulation_support = touches >= 2

            accumulation_detected = (
                consolidation_zone and 
                volume_accumulation and 
                higher_lows_pattern and 
                vwap_accumulation_support
            )

            is_breakout = current_price > highest_high
            is_breakdown = current_price < lowest_low

            return accumulation_detected, range_pct, volume_acc_ratio, is_breakout, is_breakdown
        except Exception as e:
            return False, 0, 0, False, False

    # Scenario 1: Perfect Accumulation
    # 20 candles of tight range, rising volume average, vwap support
    s1_high = [101.0] * 10 + [101.5] * 10
    s1_low = [99.5] * 10 + [100.2] * 10 # Rising lows
    s1_close = [100.5] * 20
    s1_volume = [1000] * 10 + [1500] * 10 # 1.5x volume accumulation
    df1 = pd.DataFrame({"high": s1_high, "low": s1_low, "close": s1_close, "volume": s1_volume})
    acc1, range1, vol1, brk1, bdn1 = get_acc_status(df1)
    print(f"Scenario 1 (Accumulation): Detected={acc1}, Range={range1:.2f}%, VolRatio={vol1:.2f} -> {'PASS' if acc1 else 'FAIL'}")

    # Scenario 2: Breakout Upgrade
    # Same as S1 but last candle breaks out
    df2 = df1.copy()
    df2.loc[19, "close"] = 102.0
    acc2, range2, vol2, brk2, bdn2 = get_acc_status(df2)
    print(f"Scenario 2 (Breakout): Breakout={brk2} -> {'PASS' if brk2 else 'FAIL'}")

    # Scenario 3: Invalidation (Breakdown)
    # Same as S1 but last candle breaks down
    df3 = df1.copy()
    df3.loc[19, "close"] = 99.0
    acc3, range3, vol3, brk3, bdn3 = get_acc_status(df3)
    print(f"Scenario 3 (Breakdown): Breakdown={bdn3} -> {'PASS' if bdn3 else 'FAIL'}")

if __name__ == "__main__":
    test_v34_accumulation_logic()
