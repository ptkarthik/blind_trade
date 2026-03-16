"""
V6.3 Global Market Context
Provides a shared view of current market conditions (regime, trend, sector strength).
Initialized with neutral/mixed defaults and updated during market scans.
"""

index_ctx = {
    "market_regime": "Mixed",
    "ad_ratio": 1.0,
    "market_trend": "Neutral",
    "market_bias": "Neutral",
    "day_change_pct": 0.0,
    "adx_val": 0.0,
    "score": 50,
    "sector_perfs": {},
    "sector_densities": {}
}
