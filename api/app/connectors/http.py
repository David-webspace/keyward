"""共用的 HTTP 重試：429 與 5xx 依 Retry-After 等待後重送。

寫入請求也會重試，所以呼叫端必須自己確保冪等（例如先讀狀態、或接受「已經不是成員」的 404）。
"""

import time
from collections.abc import Callable

import httpx

RETRY_STATUS = {429, 500, 502, 503, 504}


class Retrying:
    def __init__(self, http: httpx.Client, max_attempts: int = 6, max_wait: float = 30.0,
                 sleep: Callable[[float], None] = time.sleep):
        self.http, self.max_attempts, self.max_wait, self.sleep = http, max_attempts, max_wait, sleep
        self.retries = 0

    def request(self, method: str, url: str, **kw) -> httpx.Response:
        for attempt in range(1, self.max_attempts + 1):
            r = self.http.request(method, url, **kw)
            if r.status_code not in RETRY_STATUS or attempt == self.max_attempts:
                return r
            self.retries += 1
            wait = r.headers.get("Retry-After")
            self.sleep(min(float(wait) if wait and wait.isdigit() else 2 ** attempt, self.max_wait))
        raise AssertionError("unreachable")
