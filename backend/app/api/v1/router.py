from fastapi import APIRouter

from app.api.v1 import admin, auth, children, families, migrations

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(families.router)
api_router.include_router(children.router)
api_router.include_router(migrations.router)