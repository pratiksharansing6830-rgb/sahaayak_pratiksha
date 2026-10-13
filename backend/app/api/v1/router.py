from fastapi import APIRouter

from app.api.v1 import (
    admin, admin_services, auth, children, families, follow_ups, gov, migrations, needs,
    providers, referral_actions, referrals, services,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(admin_services.router)
api_router.include_router(families.router)
api_router.include_router(children.router)
api_router.include_router(migrations.router)
api_router.include_router(needs.router)
api_router.include_router(follow_ups.router)
api_router.include_router(services.router)
api_router.include_router(referrals.router)
api_router.include_router(referral_actions.router)
api_router.include_router(providers.router)
api_router.include_router(gov.router)