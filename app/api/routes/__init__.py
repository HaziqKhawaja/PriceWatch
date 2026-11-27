from fastapi import APIRouter

from app.api.routes import admin, auth, history, notifications, products, watches

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(products.router)
api_router.include_router(history.router)
api_router.include_router(watches.router)
api_router.include_router(notifications.router)
