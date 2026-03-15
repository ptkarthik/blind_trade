import sys
import os

def test_hard_filters():
    # New Mapping:
    # Score < 60 → Ignore
    # Score 60-70 → Watchlist
    # Score 70-85 → Buy Setup
    # Score > 85 → High Conviction Buy

    scenarios = [
        # Normal Scenarios (No blocks)
        {"name": "Normal Low", "score": 55, "liq": False, "neg": 0, "rvol": 1.6, "expected_signal": "IGNORE", "expected_label": "Low Probability"},
        {"name": "Normal Watchlist", "score": 65, "liq": False, "neg": 0, "rvol": 1.6, "expected_signal": "WATCHLIST", "expected_label": "Tradeable Setup"},
        {"name": "Normal Buy", "score": 75, "liq": False, "neg": 0, "rvol": 1.6, "expected_signal": "BUY SETUP", "expected_label": "High Conviction"},
        {"name": "Normal High Conv", "score": 90, "liq": False, "neg": 0, "rvol": 1.8, "expected_signal": "HIGH CONVICTION BUY", "expected_label": "👑 Pioneer Prime Candidate"},

        # Filter 1: Liquidity Safety
        {"name": "Liquidity Block", "score": 90, "liq": True, "neg": 0, "rvol": 2.0, "expected_signal": "IGNORE", "expected_label": "Insufficient liquidity"},

        # Filter 2: Score Threshold (No BUY < 70)
        {"name": "Score Threshold Buy Check", "score": 69, "liq": False, "neg": 0, "rvol": 1.6, "expected_signal": "WATCHLIST", "expected_label": "Tradeable Setup"},

        # Filter 3: Risk Dominance (Risk < -30)
        {"name": "Risk Dominance Block", "score": 90, "liq": False, "neg": -35, "rvol": 2.2, "expected_signal": "IGNORE", "expected_label": "Risk factors dominate setup"},

        # Filter 4: Volume Confirmation (RVOL < 1.5)
        {"name": "Volume Block", "score": 85, "liq": False, "neg": 0, "rvol": 1.2, "expected_signal": "IGNORE", "expected_label": "Insufficient volume confirmation"},
    ]

    print("--- Pioneer Specialist Hard Filter Verification ---")
    
    for s in scenarios:
        final_score = s["score"]
        liquidity_rejected = s["liq"]
        total_negative_score = s["neg"]
        rvol_val = s["rvol"]

        # --- REPLICATING ENGINE LOGIC ---
        block_trade = False
        block_reason = None
        
        if liquidity_rejected:
            block_trade = True
            block_reason = "Insufficient liquidity"
        elif final_score < 70:
            pass # No block, just mapping below 70
        
        if not block_trade and total_negative_score < -30:
            block_trade = True
            block_reason = "Risk factors dominate setup"
            
        if not block_trade and rvol_val < 1.5:
            block_trade = True
            block_reason = "Insufficient volume confirmation"

        signal_type = "WATCH / WAIT"
        confidence_label = "Ignore"
        
        if block_trade:
            signal_type = "IGNORE"
            confidence_label = block_reason
        else:
            if final_score >= 85:
                signal_type = "HIGH CONVICTION BUY"
                confidence_label = "👑 Pioneer Prime Candidate"
            elif final_score >= 70:
                signal_type = "BUY SETUP"
                confidence_label = "High Conviction"
            elif final_score >= 60:
                signal_type = "WATCHLIST"
                confidence_label = "Tradeable Setup"
            else:
                signal_type = "IGNORE"
                confidence_label = "Low Probability"

        print(f"Scenario: {s['name']:25} | Score: {final_score:3} | RVOL: {rvol_val:3} | Signal: {signal_type:20} | Label: {confidence_label}")
        
        if signal_type != s["expected_signal"] or confidence_label != s["expected_label"]:
            print(f"  ❌ MISMATCH! Expected: {s['expected_signal']} / {s['expected_label']}")

test_hard_filters()
