from app import scheduler as sched
from app.config import Settings
from app.services.scrape_runs import run_scrape_cycle


def test_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(sched, "get_settings", lambda: Settings(SCHEDULER_ENABLED=False))
    assert sched.start_scheduler() is None
    sched.shutdown_scheduler(None)


def test_enabled_registers_job(monkeypatch):
    monkeypatch.setattr(
        sched, "get_settings", lambda: Settings(SCHEDULER_ENABLED=True, SCRAPE_INTERVAL_MINUTES=7)
    )
    s = sched.start_scheduler()
    assert s is not None
    try:
        job = s.get_job("scrape_cycle")
        assert job is not None
        assert job.func is run_scrape_cycle
        assert job.trigger.interval.total_seconds() == 7 * 60
        assert job.max_instances == 1
        assert job.coalesce is True
    finally:
        sched.shutdown_scheduler(s)
