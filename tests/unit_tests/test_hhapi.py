import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://hh.ru/",
    "Origin": "https://hh.ru",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}
proxies = {"http": "http://127.0.0.1:10809", "https": "http://127.0.0.1:10809"}


def test_HHAPI():
    r = requests.get("https://api.hh.ru/", headers=HEADERS)
    print(r.status_code)
    print(r.text[:300])
    assert r.status_code == 200
