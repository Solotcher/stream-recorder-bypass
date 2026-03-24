"""
API 요청/응답 Pydantic 모델 통합 모듈.
기존 endpoints.py에 산재되어 있던 모델들을 한 곳에 모아 재사용성을 높입니다.
"""
from pydantic import BaseModel
from typing import Optional


class ChannelCreateRequest(BaseModel):
    """채널 등록 전용 모델"""
    platform: str
    id: str
    name: str
    resolution: Optional[str] = "best"


class ManualRecordRequest(BaseModel):
    """수동 즉시 녹화 전용 모델"""
    platform: str
    id: str
    name: str
    resolution: Optional[str] = "best"
    stream_password: Optional[str] = None


class CookieRequest(BaseModel):
    """쿠키 업데이트 요청 모델"""
    raw_cookie: str


class ConfigRequest(BaseModel):
    """시스템 설정 업데이트 요청 모델"""
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    OUTPUT_DIR: Optional[str] = None
    RCLONE_PATH: Optional[str] = None
    RCLONE_REMOTE: Optional[str] = None
    FILENAME_PATTERN: Optional[str] = None


class VodDownloadRequest(BaseModel):
    """VOD 비동기 다운로드 요청 모델"""
    url: str
