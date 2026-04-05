"""
Event-Driven 녹화 후처리 파이프라인.

recorder.py의 start_record() 내부에 하드코딩되어 있던 플랫폼별 후처리 분기를
전략(Strategy) 패턴 기반 핸들러로 분리합니다.

각 핸들러는 녹화 종료 이벤트를 수신하고, 플랫폼에 맞는 후처리를 수행합니다:
- RemuxingHandler: .ts → .mp4 리먹싱 (치지직, 트위치, 인스타)
- DirectMp4Handler: 업로드만 수행 (유튜브, 틱톡)
- SoopPartHandler: 파트 대기 알림 (SOOP)
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Optional

from app.core.logger import logger
from app.utils.telegram_bot import send_telegram_message


class PostProcessingHandler(ABC):
    """후처리 핸들러 추상 인터페이스"""

    @abstractmethod
    async def handle(
        self,
        output_path: str,
        channel_name: str,
        platform: str,
        session_part: int = 0
    ) -> None:
        """녹화 완료 후의 후처리를 수행합니다."""
        pass


class RemuxingHandler(PostProcessingHandler):
    """
    .ts → .mp4 리먹싱 후처리.
    대상: 치지직(Chzzk), 트위치(Twitch), 인스타그램(Instagram)
    Celery 우선, 실패 시 로컬 Fallback.
    """

    async def handle(
        self,
        output_path: str,
        channel_name: str,
        platform: str,
        session_part: int = 0
    ) -> None:
        from app.core.config import settings
        if settings.REMUXER_ENABLED:
            logger.info(
                f"[{channel_name}] remuxer 컨테이너 활성화 상태. "
                f"Celery 리먹싱을 스킵합니다. (파일: {output_path})"
            )
            await send_telegram_message(
                f"<b>{channel_name}</b> 녹화 종료. "
                f"remuxer 컨테이너에서 자동 후처리됩니다."
            )
            return

        from app.worker.tasks import process_remuxing_celery_task

        try:
            process_remuxing_celery_task.apply_async(
                args=[output_path, channel_name], expires=10
            )
            await send_telegram_message(
                f"<b>{channel_name}</b> 녹화 종료. "
                f"백그라운드 워커(Celery)에서 후처리(Remuxing)를 시작합니다."
            )
        except Exception as e:
            logger.warning(
                f"[{channel_name}] Celery 연동 실패({e}), "
                f"로컬 비동기 병합(Fallback)을 시작합니다."
            )
            await send_telegram_message(
                f"<b>{channel_name}</b> 녹화 종료. "
                f"로컬 시스템에서 후처리(Remuxing)를 시작합니다."
            )
            from app.services.merger import process_remuxing
            asyncio.create_task(process_remuxing(output_path, channel_name))


class DirectMp4Handler(PostProcessingHandler):
    """
    MP4 직접 녹화 완료 후처리 (리먹싱 불필요).
    대상: 유튜브(YouTube), 틱톡(TikTok)
    완료 알림 + 클라우드 업로드 트리거.
    """

    PLATFORM_NAMES = {
        "youtube": "유튜브",
        "tiktok": "틱톡",
    }

    async def handle(
        self,
        output_path: str,
        channel_name: str,
        platform: str,
        session_part: int = 0
    ) -> None:
        platform_name = self.PLATFORM_NAMES.get(platform, platform)
        await send_telegram_message(
            f"<b>{channel_name}</b> {platform_name} 녹화 완료. (.mp4)"
        )

        # 클라우드 자동 업로드 트리거
        from app.services.uploader import upload_file
        asyncio.create_task(upload_file(output_path, channel_name))


class SoopPartHandler(PostProcessingHandler):
    """
    SOOP 분할 파트 종료 후처리.
    방송 종료(방종) 시점의 일괄 병합은 scheduler.py에서 담당하므로,
    여기서는 파트 종료 알림만 전송합니다.
    """

    async def handle(
        self,
        output_path: str,
        channel_name: str,
        platform: str,
        session_part: int = 0
    ) -> None:
        await send_telegram_message(
            f"<b>{channel_name}</b> 녹화 파트({session_part}) 종료. 방종 대기 중..."
        )


# 플랫폼 → 핸들러 매핑 (Strategy 디스패치)
_HANDLER_MAP = {
    "youtube": DirectMp4Handler(),
    "tiktok": DirectMp4Handler(),
    "soop": SoopPartHandler(),
}

# 기본 핸들러 (치지직, 트위치, 인스타 등 Streamlink 플랫폼)
_DEFAULT_HANDLER = RemuxingHandler()


async def dispatch_post_processing(
    output_path: str,
    channel_name: str,
    platform: str,
    session_part: int = 0
) -> None:
    """
    플랫폼에 맞는 후처리 핸들러를 선택하고 실행합니다.

    recorder.py에서 이 함수 하나만 호출하면 됩니다.
    새 플랫폼 추가 시 _HANDLER_MAP에 핸들러를 등록하기만 하면 됩니다 (OCP 준수).
    """
    handler = _HANDLER_MAP.get(platform, _DEFAULT_HANDLER)
    logger.info(
        f"[{channel_name}] 후처리 디스패치: {handler.__class__.__name__} (platform={platform})"
    )
    await handler.handle(output_path, channel_name, platform, session_part)
