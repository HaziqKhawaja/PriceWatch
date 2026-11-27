from fastapi import APIRouter, Depends

from app.api.deps import require_admin

# Placeholder so admin-only access control is testable now.
# Real admin routes (retailers, scrape runs) arrive in milestone 4.
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}
