import os

p = r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend\app\services\ta_intraday.py"
with open(p, "r") as f:
    data = f.read()

old = """        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])"""

new = """        if not df.attrs.get("_series_ensured"):
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = IntradayTechnicalAnalysis._ensure_series(df[col])"""

data = data.replace(old, new)

with open(p, "w") as f:
    f.write(data)

print(f"Replaced {data.count(new)} occurrences.")
