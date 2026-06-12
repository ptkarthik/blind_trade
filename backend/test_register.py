import urllib.request, json, urllib.error
data = json.dumps({'username': 'testuser_admin', 'password': 'testpassword'}).encode('utf-8')
req = urllib.request.Request('http://127.0.0.1:8012/api/v1/auth/register', data=data, headers={'Content-Type': 'application/json'})
try:
    res = urllib.request.urlopen(req)
    print(res.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print(f'HTTP Error {e.code}: {e.read().decode("utf-8")}')
