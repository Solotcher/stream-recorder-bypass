import asyncio
import os
import subprocess
from app.core.config import settings
from app.core.logger import logger
from app.utils.telegram_bot import send_telegram_message

PLATFORM_URL_PATTERNS = {
    "youtube": ["youtube.com", "youtu.be"],
    "tiktok": ["tiktok.com"],
    "kick": ["kick.com"],
    "soop": ["sooplive.co.kr", "afreecatv.com"],
}

def _detect_platform(url: str) -> str:
    for platform, patterns in PLATFORM_URL_PATTERNS.items():
        if any(p in url for p in patterns):
            return platform
    return "youtube"  # 기본값

def _build_vod_command(url: str, output_dir: str, platform: str) -> list:
    if platform == "soop":
        output_template = os.path.join(output_dir, "%(uploader)s", "VOD_%(title)s.%(ext)s")
        return [settings.YTDLP_PATH, "--no-playlist", "-o", output_template, url]
    elif platform == "tiktok":
        output_template = os.path.join(output_dir, "TikTok", "%(uploader)s_%(title)s.%(ext)s")
        return [settings.YTDLP_PATH, "--no-playlist", "-o", output_template, url]
    elif platform == "kick":
        output_template = os.path.join(output_dir, "Kick", "%(uploader)s_%(title)s.%(ext)s")
        return [settings.YTDLP_PATH, "--no-playlist", "-o", output_template, url]
    else: # youtube
        output_template = os.path.join(output_dir, "%(uploader)s", "VOD_%(title)s.%(ext)s")
        return [
            settings.YTDLP_PATH,
            "--no-playlist",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "-S", "vcodec:h264,res,acodec:m4a",
            "--merge-output-format", "mp4",
            "-o", output_template,
            url
        ]

async def download_vod_task(url: str, output_dir: str = settings.OUTPUT_DIR):
    """
    VOD/영상을 백그라운드에서 다운로드하는 워커 함수입니다.
    FastAPI BackgroundTasks 내부에서 실행되도록 설계되었습니다.
    """
    platform = _detect_platform(url)
    logger.info(f"[VOD Download] {platform} 영상 다운로드 요청 시작: {url}")
    await send_telegram_message(f"🎬 <b>{platform} VOD 다운로드 시작</b>\n- URL: {url}")
    
    cmd = _build_vod_command(url, output_dir, platform)
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    
    def _wait_proc():
        stdout_data, stderr_data = proc.communicate()
        return proc.returncode, stdout_data, stderr_data
        
    try:
        returncode, stdout, stderr = await asyncio.to_thread(_wait_proc)
        if returncode == 0:
            logger.info(f"[VOD Download] {platform} 영상 다운로드 완료: {url}")
            await send_telegram_message(f"✅ <b>VOD 다운로드 완료</b>\n- URL: {url}\n서버 내 VOD 폴더에 저장되었습니다.")
        else:
            logger.error(f"[VOD Download] {platform} 영상 다운로드 실패. Code: {returncode}")
            logger.error(f"[VOD Download] stderr: {stderr[-1000:] if stderr else ''}")
            await send_telegram_message(f"❌ <b>VOD 다운로드 에러</b>\n- URL: {url}\n다운로드 도중 에러가 발생했습니다.")
            
    except Exception as e:
        logger.error(f"[VOD Download] 다운로드 프로세스 예외 발생: {e}")
        if proc.poll() is None:
            proc.kill()
        await send_telegram_message(f"❌ <b>VOD 다운로드 예외 발생</b>\n- URL: {url}\n원인: {str(e)}")
