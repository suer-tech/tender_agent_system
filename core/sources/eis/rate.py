"""Токен-бакет под лимит ДИС.

ДИС: 90 запросов / 60 сек на токен (проверено 2026-04-21 пробником). Сверх
лимита — SOAP errorInfo code=13. Сквозной rate limiter используется и phase1
(SOAP) и ретраем на code=13 (блокируем всех воркеров на 60 сек).
"""
from __future__ import annotations

import threading
import time
from collections import deque


class TokenBucket:
    """Скользящее окно: не больше `n` вызовов за `per_seconds`.

    Thread-safe. `acquire()` блокирует поток до доступного окна.
    """

    def __init__(self, n: int = 90, per_seconds: float = 60.0):
        self.n = n
        self.per = per_seconds
        self._hits: deque[float] = deque()
        self._lock = threading.Lock()
        self._pause_until: float = 0.0

    def acquire(self) -> None:
        while True:
            now = time.time()
            with self._lock:
                if now < self._pause_until:
                    wait = self._pause_until - now
                else:
                    while self._hits and now - self._hits[0] > self.per:
                        self._hits.popleft()
                    if len(self._hits) < self.n:
                        self._hits.append(now)
                        return
                    wait = self.per - (now - self._hits[0]) + 0.05
            time.sleep(max(0.05, wait))

    def pause(self, seconds: float) -> None:
        """Поставить глобальную паузу — все вызовы `acquire()` будут ждать."""
        with self._lock:
            self._pause_until = max(self._pause_until, time.time() + seconds)
