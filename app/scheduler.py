import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.services.scrape_runs import run_scrape_cycle

logger = logging.getLogger(__name__)

JOB_ID = "scrape_cycle"
FIRST_RUN_DELAY_SECONDS = 15


def start_scheduler() -> BackgroundScheduler | None:
    settings = get_settings()
    if not settings.SCHEDULER_ENABLED:
        logger.info("Scheduler disabled")
        return None
    scheduler = BackgroundScheduler(timezone=UTC)
    scheduler.add_job(
        run_scrape_cycle,
        IntervalTrigger(minutes=settings.SCRAPE_INTERVAL_MINUTES),
        id=JOB_ID,
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=datetime.now(UTC) + timedelta(seconds=FIRST_RUN_DELAY_SECONDS),
    )
    scheduler.start()
    logger.info(
        "Scheduler started: scrape every %d minutes (first run in %ds)",
        settings.SCRAPE_INTERVAL_MINUTES,
        FIRST_RUN_DELAY_SECONDS,
    )
    return scheduler


def shutdown_scheduler(scheduler: BackgroundScheduler | None) -> None:
    if scheduler is not None:
        scheduler.shutdown(wait=False)
