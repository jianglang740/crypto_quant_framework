import time
import hmac
import hashlib
import requests

API_KEY = "XcbhoFD5akW9DjkQKRyJCM2qVwN42MBSKvYx6HLeVMsHMkGlEGOKtGvcO9pmhHFz"
SECRET = "swEPIU1SteXZum4pTVMIglYJ3dhgYB3rOokjCMpeB2N8D6EW9BVkHlG3WYpn9l9j"

timestamp = int(time.time() * 1000)
query = f"timestamp={timestamp}&recvWindow=10000"
signature = hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()

url = f"https://testnet.binancefuture.com/fapi/v2/account?{query}&signature={signature}"
headers = {"X-MBX-APIKEY": API_KEY}
proxies = {
    "http": "socks5h://127.0.0.1:1080",
    "https": "socks5h://127.0.0.1:1080"
}

resp = requests.get(url, headers=headers, proxies=proxies, timeout=30)
print("状态码:", resp.status_code)
print("响应内容:", resp.text)