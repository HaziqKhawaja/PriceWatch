from app.scrapers.base import BaseScraper
from app.scrapers.betamart import BetaMartScraper
from app.scrapers.gammagoods import GammaGoodsScraper
from app.scrapers.shopalpha import ShopAlphaScraper

REGISTRY: dict[str, BaseScraper] = {
    scraper.key: scraper for scraper in (ShopAlphaScraper(), BetaMartScraper(), GammaGoodsScraper())
}


def get_scraper_by_key(key: str) -> BaseScraper | None:
    return REGISTRY.get(key)


def get_scraper_for_url(url: str) -> BaseScraper | None:
    for scraper in REGISTRY.values():
        if scraper.matches(url):
            return scraper
    return None
