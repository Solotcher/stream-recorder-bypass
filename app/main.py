from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from app.core.config import settings
from app.core.logger import logger, set_trace_id, get_trace_id, reset_trace_id
from app.api.endpoints import router as api_router
from app.services.scheduler import init_scheduler, shutdown_scheduler
import os
import sys
import asyncio
import uuid

# Windows 환경에서 subprocess (streamlink, ffmpeg) 비동기 실행 시 
# NotImplementedError 가 발생하는 것을 막기 위해 ProactorEventLoop 강제 설정
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Events
    logger.info(f"{settings.APP_NAME} {settings.VERSION} 가 시작되었습니다.")
    
    # DB 테이블 초기화 (신규 모델 자동 생성 보장)
    from app.db.session import init_db
    init_db()
    
    # 외부 의존성(FFmpeg, Streamlink) 자동 감지 및 다운로드
    from app.utils.dependency_manager import check_all_dependencies
    check_all_dependencies()
    from app.utils.dependency_manager import schedule_background_updates
    schedule_background_updates()
    
    # 서버 재부팅(Live Reload) 시 분실된 FFmpeg 프로세스(PID) 추적 및 메모리 부착
    from app.services.recorder import RecorderManager
    try:
        RecorderManager.restore_active_processes()
    except Exception as e:
        logger.error(f"프로세스 복구 실패: {e}")

    from app.services.session_manager import SessionManager
    try:
        SessionManager.restore_all_sessions()
        
        # [추가] OS 프로세스에 없는 좀비 세션 삭제
        active_sessions = SessionManager.get_all_active_sessions()
        for ch_id, session in list(active_sessions.items()):
            recorder = RecorderManager.get_instance(ch_id)
            if not recorder.is_recording:
                logger.warning(f"[{session.channel_name}] 프로세스 없는 좀비 세션 발견. 강제 파기합니다.")
                SessionManager.end_session(ch_id)
                
    except Exception as e:
        logger.error(f"세션 복구 실패: {e}")
    
    init_scheduler()
    
    yield
    
    # Shutdown Events
    logger.info(f"{settings.APP_NAME} 종료 중...")
    
    # aiohttp 글로벌 세션 정리 (리소스 누수 방지)
    from app.extractors.base_extractor import _global_session
    if _global_session and not _global_session.closed:
        await _global_session.close()
        logger.info("aiohttp 글로벌 세션이 안전하게 종료되었습니다.")
    
    shutdown_scheduler()

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.VERSION,
        description="통합 스트림 레코더 시스템 API (치지직, 숲, 유튜브, 트위치 지원)",
        lifespan=lifespan
    )

    # CORS: 환경변수로 제어 (기본값 *, 운영 시 도메인 지정 권장)
    raw_origins = settings.ALLOWED_ORIGINS
    if raw_origins.strip() == "*":
        allowed_origins = ["*"]
    else:
        allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API Key 인증 미들웨어 (설정에 API_KEY가 있을 때만 적용)
    @app.middleware("http")
    async def api_key_auth(request: Request, call_next):
        api_key = getattr(settings, "API_KEY", "")
        if api_key and request.url.path.startswith("/api"):
            req_key = request.headers.get("X-API-Key", "")
            if req_key != api_key:
                return JSONResponse(status_code=401, content={
                    "code": "AUTH_REQUIRED",
                    "message": "Invalid or missing API Key",
                    "traceId": get_trace_id()
                })
        return await call_next(request)

    # Trace ID 미들웨어 추가 (가장 먼저 실행되어야 하므로 하단에 선언)
    @app.middleware("http")
    async def trace_id_middleware(request: Request, call_next):
        req_trace_id = request.headers.get("X-Trace-Id", f"API-{str(uuid.uuid4())}")
        token = set_trace_id(req_trace_id)
        
        try:
            response = await call_next(request)
            response.headers["X-Trace-Id"] = req_trace_id
            return response
        finally:
            reset_trace_id(token)

    # 범용 글로벌 예외 핸들러 등록
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        err_msg = str(exc)
        logger.error(f"[Trace: {get_trace_id()}] 전역 예외 발생: {err_msg}")
        # 운영 환경에서는 내부 에러 상세 숨김
        display_message = err_msg if settings.DEBUG else "내부 서버 오류가 발생했습니다."
        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_SERVER_ERROR",
                "message": display_message,
                "traceId": get_trace_id()
            }
        )

    # API 라우터 등록
    app.include_router(api_router, prefix="/api", tags=["API"])

    # WebSocket 실시간 이벤트 엔드포인트
    from app.utils.event_bus import ws_manager

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        req_trace_id = f"WS-{str(uuid.uuid4())[:8]}"
        token = set_trace_id(req_trace_id)
        
        await ws_manager.connect(websocket)
        try:
            while True:
                # 클라이언트로부터의 메시지 대기 (keep-alive)
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            ws_manager.disconnect(websocket)
        finally:
            reset_trace_id(token)

    # 프론트엔드 정적 디렉토리 마운트
    frontend_dir = os.path.join(settings.BASE_DIR, "frontend")
    if os.path.exists(frontend_dir):
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

        @app.get("/")
        async def root_html():
            return FileResponse(os.path.join(frontend_dir, "index.html"))
    else:
        logger.warning("Frontend directory not found. Static GUI serving disabled.")
        @app.get("/")
        async def root():
            return {"message": f"Welcome to {settings.APP_NAME} API. (Frontend missing)"}

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

