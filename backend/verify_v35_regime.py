def classify_regime(ema20, ema50, adx_val, close, vwap):
    market_trend = "Neutral"
    if ema20 > ema50 and adx_val > 20:
        market_trend = "Bullish Trend"
    elif ema20 < ema50 and adx_val > 20:
        market_trend = "Bearish Trend"
    
    if adx_val < 18:
        market_trend = "Choppy"
        
    market_bias = "Bullish" if close > vwap else "Bearish"
    
    market_regime = "Mixed"
    if market_trend == "Bullish Trend" and market_bias == "Bullish":
        market_regime = "Strong Bullish"
    elif market_trend == "Bearish Trend" and market_bias == "Bearish":
        market_regime = "Strong Bearish"
    elif adx_val < 18:
        market_regime = "Sideways / Choppy"
    
    return market_regime, market_trend, market_bias

def apply_permission_rules(regime, final_score, probability_pct):
    block_trade = False
    block_reason = None
    signal_type = "WATCHLIST"
    
    if regime == "Strong Bearish":
        block_trade = True
        block_reason = "Market regime bearish"
        
    if block_trade:
        signal_type = "IGNORE"
        return signal_type, probability_pct, block_reason
    else:
        confidence_val = probability_pct
        if regime == "Sideways / Choppy":
            confidence_val -= 10
        
        if final_score >= 70:
            if regime == "Sideways / Choppy" and final_score <= 85:
                signal_type = "WATCHLIST"
            else:
                if final_score >= 85:
                    signal_type = "HIGH CONVICTION BUY"
                else:
                    signal_type = "BUY SETUP"
        else:
            signal_type = "WATCHLIST" if final_score >= 60 else "IGNORE"
        
        probability_pct = max(0, confidence_val)
        return signal_type, probability_pct, None

def test_v35_regime_logic():
    print("Starting V3.5 Market Regime Logic Verification...")

    # Scenario 1: Strong Bullish
    r1, t1, b1 = classify_regime(100, 95, 25, 105, 102)
    s1, c1, br1 = apply_permission_rules(r1, 75, 80)
    print(f"Scenario 1 (Strong Bullish): Regime={r1} -> Signal={s1}, Prob={c1} -> {'PASS' if r1 == 'Strong Bullish' and s1 == 'BUY SETUP' else 'FAIL'}")

    # Scenario 2: Strong Bearish (Should Block)
    r2, t2, b2 = classify_regime(95, 100, 25, 90, 92)
    s2, c2, br2 = apply_permission_rules(r2, 75, 80)
    print(f"Scenario 2 (Strong Bearish): Regime={r2} -> Signal={s2} -> {'PASS' if r2 == 'Strong Bearish' and s2 == 'IGNORE' else 'FAIL'}")

    # Scenario 3: Choppy (ADX < 18) - Should Downgrade Score < 85
    r3, t3, b3 = classify_regime(100, 95, 15, 105, 102)
    s3, c3, br3 = apply_permission_rules(r3, 80, 80)
    print(f"Scenario 3 (Choppy - Downgrade): Regime={r3} -> Signal={s3}, Prob={c3} -> {'PASS' if r3 == 'Sideways / Choppy' and s3 == 'WATCHLIST' and c3 == 70 else 'FAIL'}")

    # Scenario 4: Choppy (ADX < 18) - High Score stays BUY but lower confidence
    s4, c4, br4 = apply_permission_rules(r3, 90, 80)
    print(f"Scenario 4 (Choppy - High Score): Regime={r3} -> Signal={s4}, Prob={c4} -> {'PASS' if s4 == 'HIGH CONVICTION BUY' and c4 == 70 else 'FAIL'}")

    # Scenario 5: Mixed
    r5, t5, b5 = classify_regime(100, 95, 19, 105, 102) # ADX 19 (Not Bullish Trend, Not Choppy)
    s5, c5, br5 = apply_permission_rules(r5, 75, 80)
    print(f"Scenario 5 (Mixed): Regime={r5} -> Signal={s5} -> {'PASS' if r5 == 'Mixed' and s5 == 'BUY SETUP' else 'FAIL'}")

if __name__ == "__main__":
    test_v35_regime_logic()
