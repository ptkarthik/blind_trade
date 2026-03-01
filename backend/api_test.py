import requests
import json

base_url = "http://localhost:8011/api/v1"

with open('api_test_out.txt', 'w', encoding='utf-8') as f:
    def test_endpoint(path, mode):
        url = f"{base_url}{path}?mode={mode}"
        f.write(f"Testing: {url}\n")
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "today_debug" in path:
                    top = data["buys"][0]["symbol"] if data["buys"] else "None"
                    jid = data.get("debug_job_id", "N/A")
                    jtype = data.get("debug_job_type", "N/A")
                    f.write(f"  SUCCESS: Mode: {mode} | Top: {top} | Job: {jid} | Type: {jtype}\n")
                else:
                    debug = data.get("_debug", {})
                    first_sec = [k for k in data.keys() if k != "_debug"][0] if data else "None"
                    if first_sec != "None":
                        top = data[first_sec]["buys"][0]["symbol"] if data[first_sec]["buys"] else "None"
                    else:
                        top = "None"
                    f.write(f"  SUCCESS: Mode: {mode} | Top: {top} | Job: {debug.get('job_id')} | Type: {debug.get('job_type')}\n")
            else:
                f.write(f"  FAILED: {r.status_code} - {r.text}\n")
        except Exception as e:
            f.write(f"  ERROR: {e}\n")

    f.write("--- API DEBUG TEST (Port 8011) ---\n")
    test_endpoint("/signals/today_debug", "swing")
    test_endpoint("/signals/today_debug", "intraday")
    test_endpoint("/signals/sectors_debug", "swing")
    test_endpoint("/signals/sectors_debug", "intraday")
