"""
채널 CRUD API 라우터.
GET/POST/DELETE /channels 엔드포인트를 담당합니다.
"""
from fastapi import APIRouter, HTTPException
from app.core.logger import logger
from app.utils.channel_db import get_all_channels, add_channel, delete_channel, get_channel
from app.utils.cookie_manager import get_platform_cookies
from app.services.recorder import RecorderManager
from app.utils.event_bus import broadcast_event
from app.api.schemas import ChannelCreateRequest

router = APIRouter()


@router.get("/channels")
async def get_channels_list():
    """현재 등록된 채널 목록 및 레코더 상태 반환"""
    channels = get_all_channels()
    for ch in channels:
        recorder = RecorderManager.get_instance(ch.get("id"))
        ch["is_recording"] = recorder.is_recording
    return {"status": "success", "data": channels}


@router.post("/channels")
async def register_channel(request: ChannelCreateRequest):
    """새 채널 추가 (스트리머명 자동 파싱 포함)"""
    from app.services.scheduler import EXTRACTOR_MAP

    real_id = request.id
    if '/' in real_id:
        real_id = real_id.split('/')[0]
        request.id = real_id

    platform = request.platform
    ExtClass = EXTRACTOR_MAP.get(platform)
    if ExtClass:
        cookies = get_platform_cookies(platform)
        extractor = ExtClass(channel_id=request.id, cookies=cookies)
        try:
            info = await extractor.get_channel_info()
            parsed_name = info.get("channel_name")
            if parsed_name:
                request.name = parsed_name
        except Exception as e:
            logger.error(f"채널명 자동 파싱 실패: {e}")

    logger.info(f"신규 채널 추가: [{request.platform}] {request.name} ({request.id})")
    success = add_channel(request.dict())
    if not success:
        raise HTTPException(status_code=400, detail="Channel already exists or error occurs")
    await broadcast_event("channel_added", {"id": request.id, "platform": request.platform, "name": request.name})
    return {"status": "success"}


@router.delete("/channels/{channel_id}")
async def remove_channel(channel_id: str):
    """채널 삭제"""
    logger.info(f"채널 삭제 요청: {channel_id}")
    delete_channel(channel_id)
    await broadcast_event("channel_deleted", {"id": channel_id})
    return {"status": "success"}
