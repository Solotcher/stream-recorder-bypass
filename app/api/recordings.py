"""
녹화 제어 API 라우터.
GET /records/active, POST /records/manual/start, POST /channel/{id}/start|stop 엔드포인트를 담당합니다.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from app.core.logger import logger
from app.utils.channel_db import get_channel
from app.utils.cookie_manager import get_platform_cookies
from app.services.recorder import RecorderManager
from app.utils.event_bus import broadcast_event
from app.api.schemas import ManualRecordRequest

from app.services.session_manager import SessionManager

router = APIRouter()


@router.get("/records/active")
async def get_active_records():
    """현재 녹화 중인 세션 목록 반환 (SessionManager + RecorderManager 조합)"""
    active_jobs = []
    for ch_id, recorder in RecorderManager._instances.items():
        if recorder.is_recording:
            session = SessionManager.get_session(ch_id)
            started_at = session.started_at.isoformat() if session and session.started_at else None
            active_jobs.append({
                "id": ch_id,
                "platform": session.platform if session else "unknown",
                "name": session.channel_name if session else ch_id,
                "title": session.title if session else "",
                "category": session.category if session else "",
                "record_type": session.record_type if session else "scheduled",
                "started_at": started_at,
                "is_recording": True
            })
    return {"status": "success", "data": active_jobs}


async def _initiate_recording(
    channel_id: str,
    platform: str,
    ch_name: str,
    resolution: str,
    record_type: str,
    stream_password: Optional[str] = None
):
    """공통 서비스 함수: FFmpeg 녹화 트리거"""
    from app.services.scheduler import EXTRACTOR_MAP, trigger_recording

    recorder = RecorderManager.get_instance(channel_id)
    if recorder.is_recording:
        return {"status": "success", "message": "이미 녹화 중입니다."}

    ExtClass = EXTRACTOR_MAP.get(platform)
    if not ExtClass:
        raise HTTPException(status_code=400, detail="Unsupported platform")

    cookies = get_platform_cookies(platform)
    extractor = ExtClass(channel_id=channel_id, cookies=cookies)

    if stream_password:
        extractor.stream_password = stream_password

    try:
        is_live = await extractor.is_live()
        if is_live:
            meta = await extractor.get_metadata()
            final_ch_name = meta.get("channel_name", ch_name)
            await trigger_recording(
                channel_id, platform, final_ch_name, extractor, recorder, meta,
                record_type=record_type, resolution=resolution
            )

            if record_type == "manual":
                await broadcast_event("recording_started", {
                    "id": channel_id, "platform": platform,
                    "name": final_ch_name, "record_type": "manual"
                })

            label = "수동" if record_type == "manual" else "강제"
            return {"status": "success", "message": f"{label} 녹화 시작됨"}
        else:
            raise HTTPException(status_code=400, detail="방송이 오프라인 상태이거나 정보를 가져올 수 없습니다.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"녹화 처리 중 에러: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/records/manual/start")
async def start_manual_record(request: ManualRecordRequest):
    """수동 전용 녹화 시작 (DB 등록 거치지 않음)"""
    channel_id = request.id
    if '/' in channel_id:
        channel_id = channel_id.split('/')[0]

    return await _initiate_recording(
        channel_id=channel_id,
        platform=request.platform,
        ch_name=request.name,
        resolution=request.resolution or "best",
        record_type="manual",
        stream_password=getattr(request, "stream_password", None)
    )


@router.post("/channel/{channel_id}/start")
async def start_recording_scheduled_manual(channel_id: str):
    """예약 채널의 강제 녹화 요청"""
    logger.info(f"예약 채널의 강제 녹화 요청: {channel_id}")

    ch = get_channel(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")

    return await _initiate_recording(
        channel_id=channel_id,
        platform=ch.get("platform"),
        ch_name=ch.get("name", channel_id),
        resolution=ch.get("resolution", "best"),
        record_type="scheduled"
    )


@router.post("/channel/{channel_id}/stop")
async def stop_recording_manual(channel_id: str):
    """실행 중인 녹화 프로세스 강제 종료"""
    recorder = RecorderManager.get_instance(channel_id)
    if recorder.is_recording:
        await recorder.stop_record("사용자 강제 종료")
        await broadcast_event("recording_stopped", {"id": channel_id})
    return {"status": "success"}
