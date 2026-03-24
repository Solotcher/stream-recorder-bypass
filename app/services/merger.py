import asyncio
import os
import glob
import re
import shutil
from app.core.logger import logger
from app.core.config import settings
from app.utils.telegram_bot import send_telegram_message, send_error_alert

MIN_VALID_SIZE_BYTES = 1024  # 1KB
DEFAULT_REMUX_TIMEOUT = 120  # 120초

def resolve_ffmpeg_path() -> str:
    """FFmpeg 실행 파일 경로를 반환합니다."""
    configured = settings.FFMPEG_PATH
    if os.path.isabs(configured) and os.path.isfile(configured):
        return configured
    return shutil.which(configured) or configured

async def _run_ffmpeg_async(cmd: list, timeout: int = 300) -> tuple[int, str]:
    """비동기적으로 FFmpeg 서브프로세스를 실행하고 returncode와 stderr_text를 반환하는 공통 헬퍼입니다."""
    import subprocess
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE
    )
    
    async def _wait_with_timeout():
        try:
            def _wait_proc():
                try:
                    _, stderr_output = proc.communicate(timeout=timeout)
                    return proc.returncode, stderr_output
                except subprocess.TimeoutExpired:
                    proc.kill()
                    _, stderr_output = proc.communicate()
                    return -1, stderr_output
            return await asyncio.to_thread(_wait_proc)
        except Exception as e:
            if proc.poll() is None:
                proc.kill()
            return -1, str(e).encode()
    
    try:
        returncode, stderr_bytes = await asyncio.wait_for(_wait_with_timeout(), timeout=timeout + 10)
    except asyncio.TimeoutError:
        logger.warning(f"FFmpeg 프로세스 타임아웃 ({timeout}초 초과). 강제 종료합니다.")
        if proc.poll() is None:
            proc.kill()
        return -1, "Timeout"
    
    stderr_text = stderr_bytes.decode("utf-8", errors="replace")[-2000:] if stderr_bytes else ""
    return returncode, stderr_text

async def _verify_output_or_revert(channel_name: str, output_path: str, source_paths: list, task_name: str, telegram_title: str) -> int:
    """결과물의 크기를 검증하고, 성공 시 원본 삭제, 실패 시 결과물 삭제 및 알림을 전송하는 공통 헬퍼"""
    output_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    if output_size < MIN_VALID_SIZE_BYTES:
        logger.error(f"[{channel_name}] {task_name} 결과 파일이 비정상적으로 작습니다 ({output_size}B). 원본 파일을 보존합니다.")
        await send_error_alert(channel_name, telegram_title, f"출력 파일 크기: {output_size}B")
        if os.path.exists(output_path):
            os.remove(output_path)
        return -1
        
    logger.info(f"[{channel_name}] {task_name} 성공 ({output_size // (1024*1024)}MB). 임시 파일을 삭제합니다.")
    for path in source_paths:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                logger.warning(f"임시 파일 삭제 실패 {path}: {e}")
    return output_size

async def _handle_ffmpeg_error(channel_name: str, returncode: int, stderr_text: str, task_name: str, telegram_title: str):
    """FFmpeg 실패 시 공통 에러 로깅/알람 헬퍼"""
    logger.error(f"[{channel_name}] {task_name} 실패 (Return Code: {returncode}). 원본 파일을 보존합니다.")
    if stderr_text:
        logger.error(f"[{channel_name}] FFmpeg stderr: {stderr_text}")
    await send_error_alert(channel_name, telegram_title, f"Return Code: {returncode}")

async def _remux_ts_to_mp4(channel_name: str, final_output: str, fallback_size: int) -> tuple[str, int]:
    """ts 결과물을 mp4로 추가 변환하고 성공 시 원본 ts 삭제, 실패 시 원본 유지"""
    mp4_output = final_output[:-3] + '.mp4'
    logger.info(f"[{channel_name}] ts → mp4 리먹싱 시작: {final_output}")
    
    remux_cmd = [
        resolve_ffmpeg_path(),
        "-y", "-nostdin",
        "-i", final_output,
        "-c:v", "copy", "-c:a", "copy",
        "-movflags", "+faststart",
        mp4_output
    ]
    
    rc, err = await _run_ffmpeg_async(remux_cmd, timeout=DEFAULT_REMUX_TIMEOUT)
    if rc == 0:
        remux_size = await _verify_output_or_revert(
            channel_name, mp4_output, [final_output], "ts → mp4 변환", "변환 무결성 실패"
        )
        if remux_size > 0:
            return mp4_output, remux_size
            
    logger.warning(f"[{channel_name}] mp4 변환 실패 보완책으로 ts 원본을 유지합니다.")
    return final_output, fallback_size

def _notify_concat_success(channel_name: str, chunk_count: int, size_bytes: int, filename: str):
    file_size_mb = round(size_bytes / (1024 * 1024), 1)
    final_ext = os.path.splitext(filename)[1].upper().replace('.', '')
    msg = f"✅ <b>{channel_name}</b> 방송 녹화/병합이 완료되었습니다.\n- 총 {chunk_count}개 조각 병합\n- 파일 크기: {file_size_mb} MB\n- 최종 형식: {final_ext}"
    asyncio.create_task(send_telegram_message(msg))

async def process_remuxing(input_path: str, channel_name: str):
    if not os.path.exists(input_path):
        logger.error(f"Remuxing 파일 누락: {input_path}")
        return

    dirname = os.path.dirname(input_path)
    basename = os.path.basename(input_path)
    name_without_ext = os.path.splitext(basename)[0]
    mp4_path = os.path.join(dirname, f"{name_without_ext}.mp4")

    logger.info(f"[{channel_name}] Remuxing 시작 (.ts → .mp4): {input_path} -> {mp4_path}")
    
    cmd = [
        resolve_ffmpeg_path(),
        "-y", "-nostdin",
        "-i", input_path,
        "-c:v", "copy", "-c:a", "copy",
        "-movflags", "+faststart",
        mp4_path
    ]

    try:
        returncode, stderr_text = await _run_ffmpeg_async(cmd)

        if returncode == 0:
            output_size = await _verify_output_or_revert(
                channel_name, mp4_path, [input_path], "Remuxing", "FFmpeg Remuxing 무결성 실패"
            )
            if output_size < 0:
                return

            await send_telegram_message(f"<b>{channel_name}</b> 파일 후처리(Remuxing) 완료. (.mp4)")
            
            from app.services.uploader import upload_file
            asyncio.create_task(upload_file(mp4_path, channel_name))
        else:
            await _handle_ffmpeg_error(channel_name, returncode, stderr_text, "Remuxing", "FFmpeg Remuxing (.ts → .mp4)")
            
    except Exception as e:
        logger.error(f"[{channel_name}] Remuxing 중 예외 발생: {str(e)}")
        await send_error_alert(channel_name, "FFmpeg Remuxing 예외", str(e))

async def process_soop_concat(chunks_dir: str, base_filename: str, channel_name: str):
    logger.info(f"[{channel_name}] SOOP 조각 병합 검토 시작 (Target: {base_filename})")
    
    search_pattern = os.path.join(chunks_dir, f"{base_filename}_part*.*")
    parts = glob.glob(search_pattern)
    if not parts:
        logger.warning(f"[{channel_name}] 병합할 파일이 발견되지 않았습니다: {base_filename}")
        return
        
    parts.sort(key=lambda filepath: int(re.search(r"_part(\d+)", os.path.basename(filepath)).group(1) if re.search(r"_part(\d+)", os.path.basename(filepath)) else 0))
    ext = os.path.splitext(parts[0])[1]
    final_output = os.path.join(chunks_dir, f"{base_filename}{ext}")
    
    if len(parts) == 1:
        logger.info(f"[{channel_name}] 병합 대상이 1개뿐이므로, 이름만 변경합니다.")
        os.rename(parts[0], final_output)
        await send_telegram_message(f"<b>{channel_name}</b> 단일 파일 처리 완료.")
        from app.services.uploader import upload_file
        asyncio.create_task(upload_file(final_output, channel_name))
        return
        
    list_txt_path = os.path.join(chunks_dir, f"concat_list_{base_filename.replace(' ', '_')}.txt")
    try:
        with open(list_txt_path, "w", encoding="utf-8") as f:
            for filepath in parts:
                safe_path = filepath.replace('\\', '/')
                f.write(f"file '{safe_path}'\n")
                
        logger.info(f"[{channel_name}] 총 {len(parts)}개의 조각을 병합합니다.")
        
        cmd = [
            resolve_ffmpeg_path(),
            "-y", "-nostdin",
            "-f", "concat", "-safe", "0",
            "-i", list_txt_path,
            "-c", "copy",
            final_output
        ]
        
        returncode, stderr_text = await _run_ffmpeg_async(cmd)
        
        if returncode == 0:
            output_size = await _verify_output_or_revert(
                channel_name, final_output, parts + [list_txt_path], "병합(Concat)", "SOOP Concat 무결성 실패"
            )
            if output_size < 0:
                return

            if final_output.lower().endswith('.ts'):
                final_output, output_size = await _remux_ts_to_mp4(channel_name, final_output, output_size)

            _notify_concat_success(channel_name, len(parts), output_size, final_output)
            
            from app.services.uploader import upload_file
            asyncio.create_task(upload_file(final_output, channel_name))
        else:
            await _handle_ffmpeg_error(channel_name, returncode, stderr_text, "병합(Concat)", "SOOP FFmpeg Concat")
            
    except Exception as e:
        logger.error(f"[{channel_name}] 병합 로직 에러: {e}")
        await send_error_alert(channel_name, "SOOP FFmpeg Concat 내부 에러", str(e))
    finally:
        if os.path.exists(list_txt_path):
            try: os.remove(list_txt_path)
            except Exception: pass
