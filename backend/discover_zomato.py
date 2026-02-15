
import requests

def search_yahoo(query):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
    res = requests.get(url, headers=headers)
    data = res.json()
    for quote in data.get('quotes', []):
        print(f"Symbol: {quote.get('symbol')} | Name: {quote.get('shortname')} | Exch: {quote.get('exchange')}")

if __name__ == "__main__":
    print("Searching for Zomato candidates...")
    search_yahoo("Zomato")
