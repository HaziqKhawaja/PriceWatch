import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.routes import api_router
from app.config import get_settings
from app.db import get_db

logger = logging.getLogger("pricewatch")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if settings.SCHEDULER_ENABLED:
        # TODO(milestone 4): start the APScheduler scrape job here.
        logger.info("Scheduler enabled (not implemented yet)")
    else:
        logger.info("Scheduler disabled")
    yield


app = FastAPI(title="PriceWatch", lifespan=lifespan)
app.include_router(api_router)


@app.get("/health")
def health(db: Annotated[Session, Depends(get_db)]) -> JSONResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Health check failed")
        return JSONResponse(status_code=503, content={"detail": "database unavailable"})
    return JSONResponse(content={"status": "ok"})
