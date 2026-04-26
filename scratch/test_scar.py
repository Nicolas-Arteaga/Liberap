import requests
import json

url = "http://localhost:8000/scar/scan"
data = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
try:
    response = requests.post(url, json=data, timeout=30)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")
