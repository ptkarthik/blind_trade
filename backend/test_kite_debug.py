"""Dump the authorize page content to find the API endpoint."""
import requests
import pyotp

API_KEY = "3dabnjscghrlof6y"
USER_ID = "DWK264"
PASSWORD = "master.1"
TOTP_SECRET = "AVU7NJKPBH27FKNCMCWMFPMZ7NKQFXUY"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Kite-Version": "3"
})

# Login + TOTP
resp = session.post("https://kite.zerodha.com/api/login", data={"user_id": USER_ID, "password": PASSWORD})
request_id = resp.json()["data"]["request_id"]
totp = pyotp.TOTP(TOTP_SECRET)
session.post("https://kite.zerodha.com/api/twofa", data={
    "user_id": USER_ID, "request_id": request_id,
    "twofa_value": totp.now(), "skip_session": "true"
})

# Get authorize page
resp3 = session.get(f"https://kite.zerodha.com/connect/login?api_key={API_KEY}&v=3", allow_redirects=True)
print("=== PAGE CONTENT ===")
print(resp3.text)
