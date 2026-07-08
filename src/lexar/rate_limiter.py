"""Rate limiter adaptativo compartido por embeddings y llamadas LLM (extraido de Fases 2-3)."""
from __future__ import annotations

import threading
import time


class AdaptiveRateLimiter:
    """Espacia requests para no pisar la cuota de tokens/minuto sin conocerla de antemano.

    Arranca casi sin espera; ante un 429 duplica el intervalo entre requests, y ante cada
    exito lo reduce un poco (AIMD, como el control de congestion de TCP) para converger a la
    cuota real del proyecto.
    """

    def __init__(self, initial_interval=0.05, min_interval=0.02, max_interval=20.0):
        self._interval = initial_interval
        self._min_interval = min_interval
        self._max_interval = max_interval
        self._next_time = 0.0
        self._lock = threading.Lock()

    def wait_turn(self):
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_time)
            self._next_time = start + self._interval
        sleep_for = start - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)

    def report_success(self):
        with self._lock:
            self._interval = max(self._min_interval, self._interval * 0.97)

    def report_rate_limited(self):
        with self._lock:
            self._interval = min(self._max_interval, max(self._interval * 2, 1.0))
        return self._interval
