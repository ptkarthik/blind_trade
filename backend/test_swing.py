import requests
resp = requests.post("http://localhost:8010/api/v1/jobs/scan", json={"type": "swing_scan"})
print(resp.json())
