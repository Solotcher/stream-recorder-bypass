"""
API 라우터 통합 모듈.
기존 모놀리식 endpoints.py를 대체합니다.
각 도메인별 서브 라우터(channels, recordings, settings, vod)를 통합하여
main.py의 `from app.api.endpoints import router` 호환성을 유지합니다.
"""
from fastapi import APIRouter

from app.api.channels import router as channels_router
from app.api.recordings import router as recordings_router
from app.api.config_routes import router as settings_router
from app.api.vod import router as vod_router

router = APIRouter()

router.include_router(channels_router, tags=["Channels"])
router.include_router(recordings_router, tags=["Recordings"])
router.include_router(settings_router, tags=["Settings"])
router.include_router(vod_router, tags=["VOD"])
