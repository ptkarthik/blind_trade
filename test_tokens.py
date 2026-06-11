import urllib.request
import json

tokens = [
    "8860047698:AAGDBoo0zdqlLGNmbahfzpzKxeeijy-eYKo",
    "8860047698:AAGDBoo0zdqILGNmbahfzpzKxeeijy-eYKo",
    "8860047698:AAGDBoo0zdq1LGNmbahfzpzKxeeijy-eYKo",
    "8860047698:AAGDBoo0zdqILGNmbahfzpzKxeeijy-eYk0",
    "8860047698:AAGDBoo0zdqILGNmbahfzpzKxeijy-eYKo"
]

for token in tokens:
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if data.get("ok"):
                print(f"VALID TOKEN FOUND: {token}")
                break
    except Exception as e:
        print(f"Token {token} failed: {e}")
