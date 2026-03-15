import json
import os

# Create mock data that forces the UI to see a PIONEER PRIME signal
mock_data = {
    "Technology": {
        "buys": [
            {
                "symbol": "MOCK.NS",
                "score": 99.5,
                "signal": "PIONEER BUY",
                "confidence": "👑 A-Plus Setup",
                "verdict": "🛡️ [💎 SPECIALIST V3] PIONEER BUY (👑 A-Plus Setup) [👑 PIONEER PRIME] [🚀 RS LEADER] [💎 SQUEEZE]. [💡 ENTRY] Standard entry.",
                "logic_type": "MOMENTUM",
                "price": 100.0,
                "reasons": [{"text": "Market RS Leader", "type": "positive", "label": "ALPHA", "value": "+2.5% vs Nifty", "impact": 25}],
                "support": 95.0,
                "target": 110.0,
                "stop_loss": 95.0,
                "entry": 100.0,
                "market_cap_category": "Large"
            },
            {
                "symbol": "NORMAL.NS",
                "score": 60.0,
                "signal": "BUY",
                "confidence": "Moderate Confidence",
                "verdict": "🛡️ [💎 SPECIALIST V3] BUY. [💡 ENTRY] Standard entry.",
                "logic_type": "MOMENTUM",
                "price": 100.0,
                "reasons": [],
                "support": 95.0,
                "target": 110.0,
                "stop_loss": 95.0,
                "entry": 100.0,
                "market_cap_category": "Large"
            }
        ],
        "sells": [],
        "holds": [],
        "last_updated": "Just Now"
    }
}

os.makedirs('frontend/src/mock', exist_ok=True)
with open("frontend/src/mock/sector_mock.json", "w") as f:
    json.dump(mock_data, f, indent=4)
print("Mock data generated at frontend/src/mock/sector_mock.json")
