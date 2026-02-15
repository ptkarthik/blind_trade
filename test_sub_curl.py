import subprocess

def test_subprocess_curl():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/ZOMATO.NS?range=1d&interval=1m"
    print(f"Testing connectivity to {url} via subprocess curl.exe...")
    
    try:
        # Use absolute path to curl.exe to be safe
        result = subprocess.run(
            ["C:\\Windows\\System32\\curl.exe", "-I", "-s", url],
            capture_output=True,
            text=True,
            timeout=10
        )
        print(f"Curl Status Code (Return Code): {result.returncode}")
        print(f"Curl Output:\n{result.stdout}")
        if result.stderr:
            print(f"Curl Error Output:\n{result.stderr}")
    except Exception as e:
        print(f"Execution Error: {e}")

if __name__ == "__main__":
    test_subprocess_curl()
