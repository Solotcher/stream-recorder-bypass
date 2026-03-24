import os
import glob
import re
import shutil
import subprocess
import asyncio
from typing import List, Tuple
from celery import shared_task
from app.core.logger import logger
from app.core.config import settings

# 유틸리티 (비동기 텔레그램 봇 전송을 동기 컨텍스트에서 호출하기 위함)
def sync_send_telegram(msg: str):
    try:
        from app.utils.telegram_bot import send_telegram_message
        asyncio.run(send_telegram_message(msg))
    except Exception as e:
        logger.error(f"[Telegram Sync] 발송 실패: {e}")

def sync_send_error(channel_name: str, title: str, details: str):
    try:
        from app.utils.telegram_bot import send_error_alert
        asyncio.run(send_error_alert(channel_name, title, details))
    except Exception as e:
        logger.error(f"[Telegram Sync Error] 발송 실패: {e}")

def resolve_ffmpeg_path() -> str:
    configured = settings.FFMPEG_PATH
    if os.path.isabs(configured) and os.path.isfile(configured):
        return configured
    return shutil.which(configured) or configured

@shared_task(name="tasks.download_vod")
def download_vod_celery_task(url: str, output_dir: str = settings.OUTPUT_DIR):
    """ VOD 다운로드 Celery Task """
    logger.info(f"[Celery] VOD 다운로드 시작: {url}")
    sync_send_telegram(f"🎬 <b>VOD 다운로드 시작</b>\n- URL: {url}")
    
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
            sync_send_telegram(f"✅ <b>VOD 다운로드 완료</b>\n- URL: {url}\n서버 내 VOD 폴더에 저장되었습니다.")
        else:
            logger.error(f"[Celery] VOD 다운로드 실패. Code: {proc.returncode}\n{proc.stderr[-1000:]}")
            sync_send_telegram(f"❌ <b>VOD 다운로드 에러</b>\n- URL: {url}\n다운로드 도중 에러가 발생했습니다.")
    except Exception as e:
        logger.error(f"[Celery] VOD 다운로드 예외 발생: {e}")
        sync_send_telegram(f"❌ <b>VOD 다운로드 예외 발생</b>\n- URL: {url}\n원인: {str(e)}")

@shared_task(name="tasks.process_remuxing")
def process_remuxing_celery_task(input_path: str, channel_name: str):
    """ 리먹싱(.ts -> .mp4) Celery Task """
    if not os.path.exists(input_path):
        logger.error(f"[Celery] Remuxing 파일 누락: {input_path}")
        return

    dirname = os.path.dirname(input_path)
    basename = os.path.basename(input_path)
    name_without_ext = os.path.splitext(basename)[0]
    mp4_path = os.path.join(dirname, f"{name_without_ext}.mp4")

    logger.info(f"[{channel_name}] Celery Remuxing 시작: {input_path} -> {mp4_path}")
    
    cmd = [
        resolve_ffmpeg_path(),
        "-y", "-nostdin",
        "-i", input_path,
        "-c:v", "copy", "-c:a", "copy",
        "-movflags", "+faststart",
        mp4_path
    ]

    try:
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if proc.returncode == 0:
            output_size = os.path.getsize(mp4_path) if os.path.exists(mp4_path) else 0
            if output_size >= 1024:
                logger.info(f"[{channel_name}] Remuxing 성공, 원본(.ts) 삭제")
                os.remove(input_path)
                sync_send_telegram(f"<b>{channel_name}</b> 파일 후처리(Remuxing) 완료. (.mp4)")
                
                # Rclone Upload (동기 호출)
                try:
                    from app.services.uploader import upload_file
                    asyncio.run(upload_file(mp4_path, channel_name))
                except Exception as up_e:
                    logger.error(f"[Celery] 업로드 실패: {up_e}")
            else:
                logger.error(f"[{channel_name}] Remuxing 파일 크기 미달. 원본 유지.")
                if os.path.exists(mp4_path): os.remove(mp4_path)
        else:
            logger.error(f"[{channel_name}] Remuxing 실패 (Code: {proc.returncode})")
            sync_send_error(channel_name, "FFmpeg Remuxing 실패", f"Code: {proc.returncode}")
    except Exception as e:
        logger.error(f"[{channel_name}] Remuxing 예외 발생: {e}")
        sync_send_error(channel_name, "FFmpeg Remuxing 예외", str(e))

@shared_task(name="tasks.process_soop_concat")
def process_soop_concat_celery_task(chunks_dir: str, base_filename: str, channel_name: str):
    """ SOOP 분할 녹화 병합 Celery Task """
    logger.info(f"[{channel_name}] Celery SOOP 병합 대상 탐색: {base_filename}")
    search_pattern = os.path.join(chunks_dir, f"{base_filename}_part*.*")
    parts = glob.glob(search_pattern)
    
    if not parts:
        logger.warning(f"[{channel_name}] Celery 병합 파일 없음: {base_filename}")
        return
        
    parts.sort(key=lambda filepath: int(re.search(r"_part(\d+)", os.path.basename(filepath)).group(1) if re.search(r"_part(\d+)", os.path.basename(filepath)) else 0))
    ext = os.path.splitext(parts[0])[1]
    final_output = os.path.join(chunks_dir, f"{base_filename}{ext}")
    
    if len(parts) == 1:
        os.rename(parts[0], final_output)
        sync_send_telegram(f"<b>{channel_name}</b> 단일 파일 처리 완료.")
        try:
            from app.services.uploader import upload_file
            asyncio.run(upload_file(final_output, channel_name))
        except Exception as e:
            logger.error(f"[Celery] 업로드 실패: {e}")
        return

    list_txt_path = os.path.join(chunks_dir, f"concat_list_{base_filename.replace(' ', '_')}.txt")
    try:
        with open(list_txt_path, "w", encoding="utf-8") as f:
            for filepath in parts:
                safe_path = filepath.replace('\\', '/')
                f.write(f"file '{safe_path}'\n")
                
        cmd = [
            resolve_ffmpeg_path(),
            "-y", "-nostdin",
            "-f", "concat", "-safe", "0",
            "-i", list_txt_path,
            "-c", "copy",
            final_output
        ]
        
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if proc.returncode == 0:
            for p in parts:
                if os.path.exists(p): os.remove(p)
            logger.info(f"[{channel_name}] Celery SOOP 병합 완료.")
            sync_send_telegram(f"✅ <b>{channel_name}</b> SOOP 녹화 병합 완료 ({len(parts)}개)")
            
            # ts -> mp4 리먹싱을 연계
            if final_output.lower().endswith(".ts"):
                process_remuxing_celery_task(final_output, channel_name)
            else:
                try:
                    from app.services.uploader import upload_file
                    asyncio.run(upload_file(final_output, channel_name))
                except Exception as e:
                    pass
        else:
            logger.error(f"[{channel_name}] SOOP 병합 실패: Code {proc.returncode}")
            sync_send_error(channel_name, "SOOP FFmpeg Concat 실패", f"Code: {proc.returncode}")
            
    except Exception as e:
        logger.error(f"[{channel_name}] SOOP 병합 파이프라인 에러: {e}")
    finally:
        if os.path.exists(list_txt_path):
            try: os.remove(list_txt_path)
            except Exception: pass
