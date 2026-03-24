import asyncio
import os
import subprocess
from app.core.config import settings
from app.core.logger import logger
from app.utils.telegram_bot import send_telegram_message

async def download_vod_task(url: str, output_dir: str = settings.OUTPUT_DIR):
    """
    유튜브 VOD/영상을 백그라운드에서 다운로드하는 워커 함수입니다.
    FastAPI BackgroundTasks 내부에서 실행되도록 설계되었습니다.
    """
    logger.info(f"[VOD Download] 유튜브 영상 다운로드 요청 시작: {url}")
    await send_telegram_message(f"🎬 <b>VOD 다운로드 시작</b>\n- URL: {url}")
    
    # 저장 경로를 채널명 기반 폴더로 동적 분리하기 위해 %(uploader)s 매직 변수 사용
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
            logger.info(f"[VOD Download] 유튜브 영상 다운로드 완료: {url}")
            await send_telegram_message(f"✅ <b>VOD 다운로드 완료</b>\n- URL: {url}\n서버 내 VOD 폴더에 저장되었습니다.")
        else:
            logger.error(f"[VOD Download] 유튜브 영상 다운로드 실패. Code: {returncode}")
            logger.error(f"[VOD Download] stderr: {stderr[-1000:] if stderr else ''}")
            await send_telegram_message(f"❌ <b>VOD 다운로드 에러</b>\n- URL: {url}\n다운로드 도중 에러가 발생했습니다.")
            
    except Exception as e:
        logger.error(f"[VOD Download] 다운로드 프로세스 예외 발생: {e}")
        if proc.poll() is None:
            proc.kill()
        await send_telegram_message(f"❌ <b>VOD 다운로드 예외 발생</b>\n- URL: {url}\n원인: {str(e)}")
