import sys
import os

# Mocking parts of the system to test only the scoring logic
def test_scoring_tiers():
    scenarios = [
        {"score": 30, "expected_prob": 30, "expected_conviction": "Ignore"},
        {"score": 55, "expected_prob": 40, "expected_conviction": "Watchlist"},
        {"score": 65, "expected_prob": 50, "expected_conviction": "Tradeable Setup"},
        {"score": 75, "expected_prob": 50, "expected_conviction": "High Conviction"}, # Note: 70+ is High Conv conviction but 60-80 is 50% prob
        {"score": 85, "expected_prob": 60, "expected_conviction": "High Conviction"},
        {"score": 110, "expected_prob": 70, "expected_conviction": "High Conviction"},
        {"score": 145, "expected_prob": 80, "expected_conviction": "👑 Pioneer Prime Candidate"},
        {"score": 160, "expected_prob": 85, "expected_conviction": "👑 Pioneer Prime Candidate"}
    ]

    print("--- Pioneer Specialist V3.1 Scoring Verification ---")
    
    for s in scenarios:
        final_score = s["score"]
        
        # Tiered Probability % Calculation (V3.1)
        if final_score <= 40: prob = 30
        elif final_score <= 60: prob = 40
        elif final_score <= 80: prob = 50
        elif final_score <= 100: prob = 60
        elif final_score <= 120: prob = 70
        elif final_score <= 140: prob = 75
        elif final_score <= 150: prob = 80
        else: prob = 85

        # Signal & Conviction Labels (Pioneer Specialist Tiered V3.1)
        conviction = "Ignore"
        if final_score >= 140: conviction = "👑 Pioneer Prime Candidate"
        elif final_score >= 80: conviction = "High Conviction"
        elif final_score >= 70: conviction = "High Conviction"
        elif final_score >= 60: conviction = "Tradeable Setup"
        elif final_score >= 50: conviction = "Watchlist"

        print(f"Score: {final_score:3} | Prob: {prob:2}% | Conviction: {conviction}")
        
        if prob != s["expected_prob"] or conviction != s["expected_conviction"]:
            print(f"  ❌ MISMATCH! Expected Prob: {s['expected_prob']}, Expected Conviction: {s['expected_conviction']}")

test_scoring_tiers()
