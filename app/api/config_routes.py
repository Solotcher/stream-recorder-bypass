"""
시스템 설정 및 쿠키 관리 API 라우터.
GET/POST /config, POST/GET /cookies/* 엔드포인트를 담당합니다.
"""
from fastapi import APIRouter, HTTPException
from app.core.logger import logger
from app.utils.cookie_manager import parse_raw_cookie, update_platform_cookies, get_platform_cookies
from app.api.schemas import CookieRequest, ConfigRequest
from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """Docker 및 로드밸런서용 헬스 체크 엔드포인트"""
    return {"status": "ok", "version": getattr(settings, "VERSION", "unknown")}



@router.post("/cookies/{platform}")
async def update_cookie(platform: str, req: CookieRequest):
    """플랫폼별 쿠키 업데이트"""
    try:
        parsed = parse_raw_cookie(req.raw_cookie)
        update_platform_cookies(platform, parsed)
        return {
            "status": "success",
            "message": f"{platform} 쿠키 적용 완료",
            "parsed_keys": list(parsed.keys()),
            "key_count": len(parsed)
        }
    except Exception as e:
        logger.error(f"쿠키 파싱 실패: {e}")
        raise HTTPException(status_code=400, detail="Invalid cookie format")


@router.get("/cookies/status")
async def get_cookies_status():
    """각 플랫폼별 쿠키 적용 상태를 조회합니다."""
    platforms = ["chzzk", "twitch", "soop", "youtube", "tiktok"]
    status = {}
    for p in platforms:
        cookies = get_platform_cookies(p)
        status[p] = {
            "applied": bool(cookies and len(cookies) > 0),
            "key_count": len(cookies) if cookies else 0
        }
    return {"status": "success", "data": status}


@router.get("/config")
async def get_system_config():
    """현재 시스템 설정 조회 (토큰 마스킹 포함)"""
    from app.core.config import settings

    raw_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    masked_token = raw_token[:10] + "***" if len(raw_token) > 10 else raw_token

    return {
        "status": "success",
        "data": {
            "TELEGRAM_BOT_TOKEN": masked_token,
            "TELEGRAM_CHAT_ID": getattr(settings, "TELEGRAM_CHAT_ID", ""),
            "OUTPUT_DIR": getattr(settings, "OUTPUT_DIR", ""),
            "RCLONE_PATH": getattr(settings, "RCLONE_PATH", "rclone"),
            "RCLONE_REMOTE": getattr(settings, "RCLONE_REMOTE", ""),
            "FILENAME_PATTERN": getattr(settings, "FILENAME_PATTERN", "{date}_{streamer}_{title}_{quality}")
        }
    }


@router.post("/config")
async def update_system_config(req: ConfigRequest):
    """시스템 설정 업데이트 (.env 파일 반영)"""
    from app.utils.env_manager import update_env_file
    import os

    updates = {k: v for k, v in req.dict().items() if v is not None}

    # 마스킹된 토큰은 업데이트 대상에서 제외
    if "TELEGRAM_BOT_TOKEN" in updates:
        token_val = updates["TELEGRAM_BOT_TOKEN"]
        if not token_val or "***" in token_val:
            del updates["TELEGRAM_BOT_TOKEN"]

    if "OUTPUT_DIR" in updates and updates["OUTPUT_DIR"]:
        os.makedirs(updates["OUTPUT_DIR"], exist_ok=True)

    update_env_file(updates)
    return {"status": "success", "message": "시스템 설정이 업데이트되었습니다."}
