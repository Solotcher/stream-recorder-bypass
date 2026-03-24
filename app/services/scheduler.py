import os
import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logger import logger
from app.core.config import settings
from app.utils.channel_db import get_all_channels
from app.utils.cookie_manager import get_platform_cookies
from app.utils.telegram_bot import send_error_alert
from app.services.recorder import RecorderManager
from app.services.session_manager import SessionManager
from app.commands.filename_generator import (
    safe_text, resolve_display_quality, generate_filename, build_output_path
)
from app.commands.streamlink_builder import StreamlinkCommandBuilder
from app.commands.ytdlp_builder import YtdlpCommandBuilder

# Extractors
from app.extractors.chzzk import ChzzkExtractor
from app.extractors.twitch import TwitchExtractor
from app.extractors.soop import SoopExtractor
from app.extractors.youtube import YouTubeExtractor
from app.extractors.tiktok import TikTokExtractor
from app.extractors.instagram import InstagramExtractor

EXTRACTOR_MAP = {
    "chzzk": ChzzkExtractor,
    "twitch": TwitchExtractor,
    "soop": SoopExtractor,
    "youtube": YouTubeExtractor,
    "tiktok": TikTokExtractor,
    "instagram": InstagramExtractor
}

# 플랫폼 → 커맨드 빌더 매핑
YTDLP_PLATFORMS = {"youtube", "tiktok"}

# 글로벌 스케줄러 인스턴스
scheduler = AsyncIOScheduler()


def init_scheduler():
    """FastAPI 시작 시 스케줄러 구동"""
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler 백그라운드 모니터링 모듈이 시작되었습니다.")

        scheduler.add_job(
            check_all_channels,
            trigger=IntervalTrigger(seconds=30),
            id="main_channel_monitor",
            name="Periodic Channel Live Status Check",
            replace_existing=True
        )


def shutdown_scheduler():
    """FastAPI 종료 시 스케줄러 정리"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler가 안전하게 종료되었습니다.")

async def trigger_recording(ch_id: str, platform: str, ch_name: str, extractor, recorder, meta, record_type: str = "scheduled", resolution: str = "best"):
    """녹화 커맨드를 조립하고 프로세스를 실행합니다. (Command + SessionManager 적용)"""

    # 세션 시작/유지 처리 (SessionManager에 위임)
    session = SessionManager.start_session(
        channel_id=ch_id,
        platform=platform,
        channel_name=ch_name,
        meta=meta,
        record_type=record_type,
    )
    # RecorderManager에도 핵심 속성 동기화 (후처리 분기에서 참조)
    recorder.session_started_at = session.started_at
    recorder.session_part = session.part
    recorder.session_platform = session.platform
    recorder.session_channel_name = session.channel_name
    recorder.session_title = session.title
    recorder.session_category = session.category

    # 1) 화질 해석
    display_quality = await resolve_display_quality(
        resolution, meta.get("stream_url", ""),
        extractor.get_streamlink_args(), platform, ch_name
    )

    # 2) 빌더 선택 및 확장자 결정
    if platform in YTDLP_PLATFORMS:
        builder = YtdlpCommandBuilder(platform, ch_id)
    else:
        builder = StreamlinkCommandBuilder()

    extension = builder.get_output_extension()
    is_soop = (platform == "soop")

    # 3) 파일명 생성 및 출력 경로 결정
    filename = generate_filename(
        started_at=recorder.session_started_at,
        channel_name=ch_name,
        title=meta.get("title", ""),
        display_quality=display_quality,
        platform=platform,
        extension=extension,
        session_part=recorder.session_part,
        is_soop=is_soop,
    )
    output_path = build_output_path(ch_name, filename)

    # 4) 커맨드 조립 (빌더에 위임)
    extra_args = extractor.get_streamlink_args()
    cmd = builder.build_command(
        stream_url=meta.get("stream_url", ""),
        output_path=output_path,
        resolution=resolution,
        extra_args=extra_args,
    )

    # 5) 백그라운드 태스크로 녹화 시작
    asyncio.create_task(recorder.start_record(cmd, output_path, safe_text(ch_name), record_type))
    return True

async def check_all_channels():
    """ 주기적으로 호출되어 채널 상태를 모니터링하는 코어 태스크 (병렬 실행) """
    logger.debug("[Scheduler] 등록된 채널들의 라이브 상태를 확인합니다...")
    channels = get_all_channels()
    
    active_channels = [ch for ch in channels if ch.get("is_active", True)]
    if not active_channels:
        return
    
    async def _check_single(ch):
        from app.core.logger import trace_id
        import uuid
        
        platform = ch.get("platform", "unknown")
        ch_id = ch.get("id", "unknown")
        ch_name = ch.get("name", ch_id)
        
        short_id = str(uuid.uuid4())[:8]
        new_trace_id = f"SCH-{platform.upper()}-{short_id}"
        token = trace_id.set(new_trace_id)
        
        try:
            ExtClass = EXTRACTOR_MAP.get(platform)
            if not ExtClass:
                return
                
            cookies = get_platform_cookies(platform)
            extractor = ExtClass(channel_id=ch_id, cookies=cookies)
            is_live = await extractor.is_live()
            recorder = RecorderManager.get_instance(ch_id)
            
            if is_live and not recorder.is_recording:
                meta = await extractor.get_metadata()
                resolution = ch.get("resolution", "best")
                
                # meta에서 가져온 실제 채널명이 있으면 우선 사용 (DB에 ID만 저장된 경우 대응)
                real_name = meta.get("channel_name", ch_name)
                if real_name and real_name != ch_id:
                    ch_name = real_name
                    # DB에도 실제 채널명을 영속화
                    from app.utils.channel_db import update_channel
                    update_channel(ch_id, {"name": ch_name})
                
                await trigger_recording(ch_id, platform, ch_name, extractor, recorder, meta, resolution=resolution)
                
            elif not is_live:
                if recorder.is_recording:
                    logger.info(f"[{ch_name}] 방종 감지. 레코더 자체 안전 중지(EOF)를 대기합니다.")
                else:
                    session = SessionManager.get_session(ch_id)
                    if session:
                        logger.info(f"[{ch_name}] 채널 오프라인 확정. 세션을 종료하고 후처리를 진행합니다.")
                        if session.platform == "soop" and session.part > 0:
                            from app.worker.tasks import process_soop_concat_celery_task
                            safe_name = safe_text(session.channel_name)
                            base_filename = f"[{session.started_at.strftime('%y%m%d_%H%M')}] {safe_name}_{session.platform}"
                            streamer_dir = os.path.join(settings.OUTPUT_DIR, safe_name)
                            try:
                                process_soop_concat_celery_task.apply_async(args=[streamer_dir, base_filename, session.channel_name], expires=10)
                            except Exception as e:
                                logger.warning(f"[{session.channel_name}] Celery 연동 실패({e}), 로컬 비동기 단일 병합(Fallback)을 수행합니다.")
                                from app.services.merger import process_soop_concat
                                asyncio.create_task(process_soop_concat(streamer_dir, base_filename, session.channel_name))

                        # 세션 종료 (SessionManager + RecorderManager 양쪽 정리)
                        SessionManager.end_session(ch_id)
                        recorder.session_started_at = None
                        recorder.session_part = 0
                
        except Exception as e:
            logger.error(f"[{ch_name}] 모니터링 중 오류 발생: {e}")
        finally:
            trace_id.reset(token)

    await asyncio.gather(*[_check_single(ch) for ch in active_channels], return_exceptions=True)
