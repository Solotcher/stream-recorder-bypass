"""
FILENAME_PATTERN 기반 녹화 파일명 생성기.
기존 scheduler.py L73-121의 파일명 생성 로직을 일원화합니다.
"""
import os
from datetime import datetime

from app.core.config import settings
from app.utils.stream_quality import resolve_best_quality, format_quality_display
from app.core.logger import logger

MAX_FILENAME_LENGTH = 200  # 파일 시스템 안전 길이 제한


def safe_text(text: str) -> str:
    """파일명에 사용할 수 없는 문자를 제거합니다."""
    return "".join(c for c in text if c.isalnum() or c in (' ', '-', '_')).rstrip()


async def resolve_display_quality(
    resolution: str,
    stream_url: str,
    streamlink_args: list,
    platform: str,
    channel_name: str
) -> str:
    """
    'best' 해상도를 실제 화질 문자열로 해석하고 표시용 포맷을 반환합니다.

    Args:
        resolution: 사용자 설정 화질 (best, 1080p60 등)
        stream_url: 스트림 URL (resolve_best_quality에 전달)
        streamlink_args: extractor.get_streamlink_args() 결과
        platform: 플랫폼 문자열
        channel_name: 로그 표시용 채널명

    Returns:
        표시용 화질 문자열 (예: '1080P60', '최고화질')
    """
    actual_resolution = resolution

    if resolution == "best":
        try:
            actual_resolution = await resolve_best_quality(
                stream_url, streamlink_args, platform=platform
            )
            logger.info(f"[{channel_name}] best → 실제 해상도 조회 결과: {actual_resolution}")
        except Exception as e:
            logger.warning(f"[{channel_name}] 실제 해상도 조회 실패, 폴백 적용: {e}")
            actual_resolution = "best"

    return format_quality_display(actual_resolution)


def generate_filename(
    started_at: datetime,
    channel_name: str,
    title: str,
    display_quality: str,
    platform: str,
    extension: str,
    session_part: int = 0,
    is_soop: bool = False,
) -> str:
    """
    FILENAME_PATTERN에 변수를 치환하여 최종 파일명을 생성합니다.

    Args:
        started_at: 세션 시작 시각
        channel_name: 스트리머명 (안전 문자 변환 전 원본)
        title: 방송 제목
        display_quality: 표시용 화질 (resolve_display_quality 결과)
        platform: 플랫폼 문자열
        extension: 파일 확장자 (.ts, .mp4 등)
        session_part: SOOP 분할 파트 번호 (0이면 파트 없음)
        is_soop: SOOP 분할 모드 여부

    Returns:
        확장자를 포함한 완전한 파일명 문자열
    """
    safe_name = safe_text(channel_name)
    safe_title = safe_text(title) if title else "제목없음"
    date_str = started_at.strftime("%Y%m%d")
    time_str = started_at.strftime("%H%M%S")

    pattern = settings.FILENAME_PATTERN
    filename_base = pattern.format(
        date=date_str,
        time=time_str,
        streamer=safe_name,
        title=safe_title,
        quality=display_quality,
        platform=platform
    )

    # 파일명 길이 제한
    if len(filename_base) > MAX_FILENAME_LENGTH:
        filename_base = filename_base[:MAX_FILENAME_LENGTH]

    # SOOP 분할 파트 접미사
    if is_soop and session_part > 0:
        return f"{filename_base}_part{session_part}{extension}"

    return f"{filename_base}{extension}"


def build_output_path(channel_name: str, filename: str) -> str:
    """스트리머별 출력 폴더를 생성하고 전체 경로를 반환합니다."""
    safe_name = safe_text(channel_name)
    streamer_dir = os.path.join(settings.OUTPUT_DIR, safe_name)
    os.makedirs(streamer_dir, exist_ok=True)
    return os.path.join(streamer_dir, filename)
