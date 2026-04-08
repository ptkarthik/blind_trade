import os

file_path = "c:/Users/Karthik/.gemini/antigravity/scratch/blind_trade/backend/app/services/ta_intraday.py"
with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

replacements = {
    # RVOL / Volume
    "latest['volume'] / vol_ma, 2) if vol_ma > 0 else 0": "latest['volume'] / max(vol_ma, 1e-6), 2)",
    "opening_vol / vol_ma if vol_ma > 0 else 1.0": "opening_vol / max(vol_ma, 1e-6)",
    "l_vol_val / vol_ma if vol_ma > 0 else 1.0": "l_vol_val / max(vol_ma, 1e-6)",
    "l_vol_val / vol_ma if not np.isnan(vol_ma) and vol_ma > 0 else 1.0": "l_vol_val / max(vol_ma, 1e-6)",
    "current_vol / avg_vol_at_time": "current_vol / max(avg_vol_at_time, 1e-6)",
    "current_vol / avg_candle_vol if avg_candle_vol > 0 else 1.0": "current_vol / max(avg_candle_vol, 1e-6)",

    # ATR
    "dist_from_ema / atr if atr > 0 else 0": "dist_from_ema / max(atr, 1e-6)",
    "candle_range / atr_val": "candle_range / max(atr_val, 1e-6)",
    "abs(l_close_val - vwap) / atr_val": "abs(l_close_val - vwap) / max(atr_val, 1e-6)",
    "(local_high - l_low_val) / atr_val": "(local_high - l_low_val) / max(atr_val, 1e-6)",
    "(micro_cons_range / (atr_val if atr_val > 0 else 1))": "(micro_cons_range / max(atr_val, 1e-6))",
    "(l_close_val - l_open_val) / (atr_val if atr_val > 0 else 1)": "(l_close_val - l_open_val) / max(atr_val, 1e-6)",
    "abs(l_close_val - breakout_level) / (atr_val if atr_val > 0 else 1)": "abs(l_close_val - breakout_level) / max(atr_val, 1e-6)",
    "(l_close_val - breakout_level) / (atr_val if atr_val > 0 else 1)": "(l_close_val - breakout_level) / max(atr_val, 1e-6)",
    "(close - best_entry) / atr_val if atr_val > 0 else 0": "(close - best_entry) / max(atr_val, 1e-6)",

    # VWAP Divs
    "abs(current_price - vwap) / current_price": "abs(current_price - vwap) / max(current_price, 1e-6)",
    "abs(l_low_val - vwap) / l_close_val": "abs(l_low_val - vwap) / max(l_close_val, 1e-6)",
    "abs(vwap_res - current_price) / current_price": "abs(vwap_res - current_price) / max(current_price, 1e-6)",
    
    # ADX / other structural if present (like close distances)
    "abs(l_low_val - ema9_val) / l_close_val": "abs(l_low_val - ema9_val) / max(l_close_val, 1e-6)",
    "abs(l_low_val - breakout_level) / l_close_val": "abs(l_low_val - breakout_level) / max(l_close_val, 1e-6)",
}

for old, new in replacements.items():
    text = text.replace(old, new)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(text)

print("Patch applied to ta_intraday.py!")
