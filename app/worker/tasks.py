"""
Celery Worker Task 모듈.
merger.py의 핵심 로직을 동기 래퍼로 호출하여 DRY 원칙을 준수합니다.
"""
import os
import subprocess
import asyncio
from celery import shared_task
from app.core.logger import logger
from app.core.config import settings
from app.services.merger import resolve_ffmpeg_path


# --- 동기 유틸리티 (Celery Worker 컨텍스트용) ---

def _sync_send_telegram(msg: str):
    """비동기 텔레그램 봇 전송을 동기 컨텍스트에서 호출"""
    try:
        from app.utils.telegram_bot import send_telegram_message
        asyncio.run(send_telegram_message(msg))
    except Exception as e:
        logger.error(f"[Telegram Sync] 발송 실패: {e}")


def _sync_upload(file_path: str, channel_name: str):
    """비동기 업로드를 동기 컨텍스트에서 호출"""
    try:
        from app.services.uploader import upload_file
        asyncio.run(upload_file(file_path, channel_name))
    except Exception as e:
        logger.error(f"[Celery] 업로드 실패: {e}")


# --- Celery Tasks ---

@shared_task(name="tasks.download_vod")
def download_vod_celery_task(url: str, output_dir: str = settings.OUTPUT_DIR):
    """VOD 다운로드 Celery Task (yt-dlp 직접 호출, 별도 래퍼 불필요)"""
    logger.info(f"[Celery] VOD 다운로드 시작: {url}")
    _sync_send_telegram(f"🎬 <b>VOD 다운로드 시작</b>\n- URL: {url}")

    output_template = os.path.join(output_dir, "%(uploader)s", "VOD_%(title)s.%(ext)s")
    cmd = [
        settings.YTDLP_PATH,
        "--no-playlist",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "-S", "vcodec:h264,res,acodec:m4a",
        "--merge-output-format", "mp4",
        "-o", output_template,
        url
    ]

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        if proc.returncode == 0:
            logger.info(f"[Celery] VOD 다운로드 완료: {url}")
            _sync_send_telegram(f"✅ <b>VOD 다운로드 완료</b>\n- URL: {url}\n서버 내 VOD 폴더에 저장되었습니다.")
        else:
            logger.error(f"[Celery] VOD 다운로드 실패. Code: {proc.returncode}\n{proc.stderr[-1000:]}")
            _sync_send_telegram(f"❌ <b>VOD 다운로드 에러</b>\n- URL: {url}\n다운로드 도중 에러가 발생했습니다.")
    except Exception as e:
        logger.error(f"[Celery] VOD 다운로드 예외 발생: {e}")
        _sync_send_telegram(f"❌ <b>VOD 다운로드 예외 발생</b>\n- URL: {url}\n원인: {str(e)}")


@shared_task(name="tasks.process_remuxing")
def process_remuxing_celery_task(input_path: str, channel_name: str):
    """리먹싱(.ts → .mp4) Celery Task. merger.py의 로직을 동기 래퍼로 호출."""
    logger.info(f"[Celery] Remuxing 위임: {input_path}")
    try:
        from app.services.merger import process_remuxing
        asyncio.run(process_remuxing(input_path, channel_name))
    except Exception as e:
        logger.error(f"[Celery] Remuxing 위임 실패: {e}")
        _sync_send_telegram(f"❌ <b>{channel_name}</b> Celery Remuxing 예외: {str(e)}")


@shared_task(name="tasks.process_soop_concat")
def process_soop_concat_celery_task(chunks_dir: str, base_filename: str, channel_name: str):
    """SOOP 분할 녹화 병합 Celery Task. merger.py의 로직을 동기 래퍼로 호출."""
    logger.info(f"[Celery] SOOP 병합 위임: {base_filename}")
    try:
        from app.services.merger import process_soop_concat
        asyncio.run(process_soop_concat(chunks_dir, base_filename, channel_name))
    except Exception as e:
        logger.error(f"[Celery] SOOP 병합 위임 실패: {e}")
        _sync_send_telegram(f"❌ <b>{channel_name}</b> Celery SOOP 병합 예외: {str(e)}")
