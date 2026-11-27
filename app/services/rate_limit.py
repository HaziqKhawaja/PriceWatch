import threading
import time
from collections.abc import Callable


class DomainRateLimiter:
    """Ensure at least `rate_limit_seconds` between requests to the same domain."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_allowed: dict[str, float] = {}

    def wait(self, domain: str, rate_limit_seconds: float) -> None:
        with self._lock:
            now = self._clock()
            slot = max(now, self._next_allowed.get(domain, now))
            self._next_allowed[domain] = slot + max(rate_limit_seconds, 0)
        delay = slot - now
        if delay > 0:
            self._sleep(delay)


rate_limiter = DomainRateLimiter()
