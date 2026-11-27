import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import Retailer
from app.services.auth import create_user, get_user_by_email

logger = logging.getLogger(__name__)

RETAILERS = [
    {"name": "ShopAlpha", "domain": "shopalpha.mock", "scraper_key": "shopalpha"},
    {"name": "BetaMart", "domain": "betamart.mock", "scraper_key": "betamart"},
    {"name": "GammaGoods", "domain": "gammagoods.mock", "scraper_key": "gammagoods"},
]


def seed_retailers(db: Session) -> None:
    for data in RETAILERS:
        retailer = db.scalar(select(Retailer).where(Retailer.domain == data["domain"]))
        if retailer is None:
            db.add(Retailer(**data, active=True, rate_limit_seconds=1))
        else:
            retailer.name = data["name"]
            retailer.scraper_key = data["scraper_key"]
    db.commit()


def seed_admin(db: Session) -> None:
    settings = get_settings()
    if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        logger.info("ADMIN_EMAIL/ADMIN_PASSWORD not set; skipping admin seed")
        return
    if get_user_by_email(db, settings.ADMIN_EMAIL) is not None:
        logger.info("Admin user already exists; skipping")
        return
    create_user(db, settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD, role="admin")
    logger.info("Seeded admin user")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        seed_retailers(db)
        seed_admin(db)
    logger.info("Seeded %d retailers", len(RETAILERS))


if __name__ == "__main__":
    main()
