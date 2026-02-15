
import numpy as np
import math

def sanitize_data(data):
    """
    Recursively converts non-serializable types (numpy, etc.) to standard Python types.
    """
    if isinstance(data, dict):
        return {k: sanitize_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_data(i) for i in data]
    elif isinstance(data, (np.bool_, bool)):
        return bool(data)
    elif isinstance(data, (np.integer, int)):
        return int(data)
    elif isinstance(data, (np.floating, float)):
        if math.isnan(data) or math.isinf(data):
            return 0.0
        return float(data)
    return data

# NSE 500 / Full Market List (Placeholder for now - intended to be dynamic)
# In production, this should be fetched from an external source or a local CSV update
STATIC_FULL_LIST = [
    # Add top 50 for testing, expandable to 500+
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "ITC", "SBIN", "BHARTIARTL", "HINDUNILVR", "LICI",
    "KOTAKBANK", "LT", "BAJFINANCE", "HCLTECH", "ADANIENT", "ASIANPAINT", "TITAN", "MARUTI", "SUNPHARMA",
    "AXISBANK", "BAJAJFINSV", "ULTRACEMCO", "TATAMOTORS", "ADANIPORTS", "NTPC", "WIPRO", "ONGC", "JSWSTEEL",
    "POWERGRID", "M&M", "LTIM", "ADANIGREEN", "COALINDIA", "TATASTEEL", "SIEMENS", "PIDILITIND", "HAL",
    "NESTLEIND", "SBILIFE", "IOC", "GRASIM", "DLF", "TECHM", "BRITANNIA", "VBL", "ZOMATO", "GODREJCP",
    "HINDALCO", "TATACONSUM", "EICHERMOT", "DIVISLAB", "DRREDDY", "BPCL", "HEROMOTOCO", "INDUSINDBK"
    # ... mapped to .NS suffix in market_service
]
