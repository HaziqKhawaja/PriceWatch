from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession, require_admin
from app.models import Retailer, ScrapeRun
from app.schemas.admin import RetailerCreate, RetailerRead, RetailerUpdate, ScrapeRunRead
from app.schemas.common import Page
from app.services.scrape_runs import RunInProgressError, execute_scrape_run, start_scrape_run

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# Plain list (not Page): the retailers table is small.
@router.get("/retailers", response_model=list[RetailerRead])
def list_retailers(db: DbSession):
    return db.scalars(select(Retailer).order_by(Retailer.id)).all()


@router.post("/retailers", response_model=RetailerRead, status_code=status.HTTP_201_CREATED)
def create_retailer(payload: RetailerCreate, db: DbSession):
    conflict = HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="Retailer domain already exists"
    )
    if db.scalar(select(Retailer.id).where(Retailer.domain == payload.domain)) is not None:
        raise conflict
    retailer = Retailer(**payload.model_dump())
    db.add(retailer)
    try:
        db.commit()
    except IntegrityError:  # concurrent insert of the same domain
        db.rollback()
        raise conflict from None
    db.refresh(retailer)
    return retailer


@router.patch("/retailers/{retailer_id}", response_model=RetailerRead)
def update_retailer(retailer_id: int, payload: RetailerUpdate, db: DbSession):
    retailer = db.get(Retailer, retailer_id)
    if retailer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retailer not found")
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(retailer, field, value)
    db.commit()
    db.refresh(retailer)
    return retailer


@router.post("/scrape-runs", response_model=ScrapeRunRead, status_code=status.HTTP_202_ACCEPTED)
def trigger_scrape_run(db: DbSession, background_tasks: BackgroundTasks):
    try:
        run = start_scrape_run(db)
    except RunInProgressError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A scrape run is already in progress"
        ) from None
    background_tasks.add_task(execute_scrape_run, run.id)
    return run


@router.get("/scrape-runs", response_model=Page[ScrapeRunRead])
def list_scrape_runs(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    total = db.scalar(select(func.count()).select_from(ScrapeRun)) or 0
    items = db.scalars(
        select(ScrapeRun)
        .order_by(ScrapeRun.started_at.desc(), ScrapeRun.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return Page[ScrapeRunRead](items=items, total=total, limit=limit, offset=offset)
