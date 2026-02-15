import http.client
import socket

def test_conn():
    targets = ["www.google.com", "finance.yahoo.com"]
    for host in targets:
        print(f"\n--- Testing {host} ---")
        try:
            # Socket test
            print(f"Resolving {host}...")
            ip = socket.gethostbyname(host)
            print(f"IP: {ip}")
            
            # HTTP test
            print(f"HTTP GET to {host}...")
            conn = http.client.HTTPSConnection(host, timeout=5)
            conn.request("GET", "/")
            res = conn.getresponse()
            print(f"Status: {res.status} {res.reason}")
        except Exception as e:
            print(f"Error for {host}: {e}")

if __name__ == "__main__":
    test_conn()
