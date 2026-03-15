
import pandas as pd
from datetime import datetime
import asyncio

# Mocking the core logic for V3.2 - Cleaned of Emojis for Terminal Safety
def test_v32_logic_standalone():
    print("Starting Stand-alone V3.2 Logic Verification...")
    
    def get_signal(score, adv, rvol, time_str):
        now_time = datetime.strptime(time_str, "%H:%M").time()
        block_trade = False
        block_reason = None
        
        # 1. Time Guard: Avoid before 09:25 AM
        if now_time < datetime.strptime("09:25", "%H:%M").time():
            block_trade = True
            block_reason = "Opening volatility guard (pre-09:25)"

        # 2. Liquidity Safety Filters
        elif adv < 200000 and rvol < 2.5:
            block_trade = True
            block_reason = "Extremely low liquidity"
        elif adv < 500000 and rvol < 2.0:
            block_trade = True
            block_reason = "Low liquidity - insufficient volume confirmation"
        
        # 3. Apply Signal Mapping & Eligibility
        if block_trade:
            if "Low liquidity" in block_reason:
                signal_type = "WATCHLIST"
            else:
                signal_type = "IGNORE"
            return signal_type, block_reason
        else:
            is_liquid_enough = (adv >= 500000) or (adv < 500000 and rvol >= 2.5)
            
            if score >= 70 and is_liquid_enough:
                if score >= 85:
                    return "HIGH CONVICTION BUY", "Pioneer Prime"
                else:
                    return "BUY SETUP", "High Conviction"
            elif score >= 60:
                return "WATCHLIST", "Tradeable Setup"
            else:
                return "IGNORE", "Low Probability"

    scenarios = [
        {"score": 80, "adv": 150000, "rvol": 1.5, "time": "10:00", "expected": "IGNORE"},
        {"score": 80, "adv": 150000, "rvol": 3.0, "time": "10:00", "expected": "BUY SETUP"},
        {"score": 80, "adv": 350000, "rvol": 1.5, "time": "10:00", "expected": "WATCHLIST"},
        {"score": 80, "adv": 350000, "rvol": 2.1, "time": "10:00", "expected": "BUY SETUP"},
        {"score": 80, "adv": 350000, "rvol": 1.9, "time": "10:00", "expected": "WATCHLIST"},
        {"score": 85, "adv": 1000000, "rvol": 1.2, "time": "09:20", "expected": "IGNORE"},
        {"score": 85, "adv": 1000000, "rvol": 1.2, "time": "09:30", "expected": "HIGH CONVICTION BUY"},
        {"score": 65, "adv": 1000000, "rvol": 1.2, "time": "10:00", "expected": "WATCHLIST"},
        {"score": 55, "adv": 1000000, "rvol": 1.2, "time": "10:00", "expected": "IGNORE"},
    ]

    print(f"{'Score':<6} | {'ADV':<8} | {'RVOL':<5} | {'Time':<6} | {'Expected':<20} | {'Actual':<20} | {'Status'}")
    print("-" * 100)
    for s in scenarios:
        actual, reason = get_signal(s["score"], s["adv"], s["rvol"], s["time"])
        # Simple ASCII status
        status = "PASS" if actual == s["expected"] else "FAIL"
        print(f"{s['score']:<6} | {s['adv']:<8} | {s['rvol']:<5} | {s['time']:<6} | {s['expected']:<20} | {actual:<20} | {status}")

if __name__ == "__main__":
    test_v32_logic_standalone()
