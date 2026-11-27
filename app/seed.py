import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Retailer

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


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        seed_retailers(db)
        # TODO(milestone 2): seed the admin user from ADMIN_EMAIL / ADMIN_PASSWORD.
    logger.info("Seeded %d retailers", len(RETAILERS))


if __name__ == "__main__":
    main()
