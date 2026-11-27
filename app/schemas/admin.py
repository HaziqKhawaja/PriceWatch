import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.scrapers.registry import get_scraper_by_key

_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$")


def _check_domain(value: str) -> str:
    value = value.strip().lower()
    if "://" in value or any(c in value for c in "/:?#@ "):
        raise ValueError("Domain must be a bare hostname (no scheme, port, or path)")
    if not _DOMAIN_RE.match(value):
        raise ValueError("Invalid domain")
    return value


def _check_scraper_key(value: str) -> str:
    if get_scraper_by_key(value) is None:
        raise ValueError(f"Unknown scraper_key '{value}'")
    return value


Domain = Annotated[str, AfterValidator(_check_domain)]
ScraperKey = Annotated[str, AfterValidator(_check_scraper_key)]


class RetailerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    domain: str
    scraper_key: str
    active: bool
    rate_limit_seconds: int


class RetailerCreate(BaseModel):
    name: Annotated[str, Field(min_length=1)]
    domain: Domain
    scraper_key: ScraperKey
    rate_limit_seconds: Annotated[int, Field(ge=0)] = 1
    active: bool = True


class RetailerUpdate(BaseModel):
    name: Annotated[str | None, Field(min_length=1)] = None
    scraper_key: ScraperKey | None = None
    active: bool | None = None
    rate_limit_seconds: Annotated[int | None, Field(ge=0)] = None


class ScrapeRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: datetime | None
    products_attempted: int
    succeeded: int
    failed: int
    error_summary: str | None
