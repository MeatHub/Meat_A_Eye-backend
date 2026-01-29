from fastapi import APIRouter
from . import auth, fridge, ai, meat, my, notifications

router = APIRouter(prefix="/api/v1", tags=["v1"])

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(fridge.router, prefix="/fridge", tags=["fridge"])
router.include_router(ai.router, prefix="/ai", tags=["ai"])
router.include_router(meat.router, prefix="/meat", tags=["meat"])
router.include_router(my.router, prefix="/my", tags=["my"])
router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
