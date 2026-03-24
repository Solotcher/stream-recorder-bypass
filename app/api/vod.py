"""
VOD 다운로드 API 라우터.
POST /vod/download 엔드포인트를 담당합니다.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.core.logger import logger
from app.api.schemas import VodDownloadRequest

router = APIRouter()


@router.post("/vod/download")
async def trigger_vod_download(request: VodDownloadRequest, background_tasks: BackgroundTasks):
    """유튜브 등 VOD 비동기 다운로드 트리거 (Celery 및 Fallback 기반)"""
    from app.worker.tasks import download_vod_celery_task
    from app.core.config import settings

    if not request.url:
        raise HTTPException(status_code=400, detail="URL is required")

    logger.info(f"VOD 다운로드 요청 접수: {request.url}")

    try:
        download_vod_celery_task.apply_async(args=[request.url, settings.OUTPUT_DIR], expires=10)
        return {"status": "success", "message": "백그라운드 큐(Celery)에서 다중 다운로드를 시작합니다."}
    except Exception as e:
        logger.warning(f"Celery 큐 접근 실패({e}). 로컬 시스템(Fallback)에서 다운로드를 시작합니다.")
        from app.services.vod_downloader import download_vod_task
        background_tasks.add_task(download_vod_task, request.url, settings.OUTPUT_DIR)
        return {"status": "success", "message": "로컬 시스템에서 단일 다운로드를 시작합니다."}
