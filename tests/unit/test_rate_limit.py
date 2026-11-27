from app.services.rate_limit import DomainRateLimiter


class FakeTime:
    def __init__(self):
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def make():
    t = FakeTime()
    return t, DomainRateLimiter(clock=t.clock, sleep=t.sleep)


def test_second_call_waits_remainder():
    t, limiter = make()
    limiter.wait("a.mock", 5)
    assert t.sleeps == []
    t.now += 2
    limiter.wait("a.mock", 5)
    assert t.sleeps == [3]


def test_no_wait_after_interval_elapsed():
    t, limiter = make()
    limiter.wait("a.mock", 5)
    t.now += 10
    limiter.wait("a.mock", 5)
    assert t.sleeps == []


def test_different_domains_independent():
    t, limiter = make()
    limiter.wait("a.mock", 5)
    limiter.wait("b.mock", 5)
    assert t.sleeps == []


def test_zero_limit_never_waits():
    t, limiter = make()
    for _ in range(3):
        limiter.wait("a.mock", 0)
    assert t.sleeps == []
