import asyncio
import os
import shlex
import subprocess
import psutil
from datetime import datetime
from typing import Optional
from app.core.config import settings
from app.core.logger import logger
from app.utils.telegram_bot import send_telegram_message, send_error_alert
from app.utils.process_state import register_process, unregister_process
from app.utils.event_bus import broadcast_event

class RecorderManager:
    """
    FFmpeg / Streamlink 서브프로세스를 통합 관리하는 서비스 클래스
    """
    
    _instances = {}

    @classmethod
    def get_instance(cls, channel_id: str):
        if channel_id not in cls._instances:
            cls._instances[channel_id] = RecorderManager(channel_id)
        return cls._instances[channel_id]

    @classmethod
    def restore_active_processes(cls):
        """ 서버 재부팅 시 OS에 살아있는 PID를 찾아서 메모리에 다시 부착(Re-attach) 처리 """
        from app.utils.process_state import cleanup_and_get_active_processes
        active_dict = cleanup_and_get_active_processes()
        
        for ch_id, info in active_dict.items():
            pid = info.get("pid")
            meta = info.get("metadata", {})
            try:
                proc = psutil.Process(pid)
                manager = cls.get_instance(ch_id)
                manager.is_recording = True
                manager.process = proc
                manager.session_platform = meta.get("platform", "unknown")
                manager.session_channel_name = meta.get("name", ch_id)
                manager.session_title = meta.get("title", "")
                manager.session_record_type = meta.get("record_type", "scheduled")
                manager.output_path = meta.get("output_path", "")
                manager.session_part = meta.get("part", 0)
                
                logger.info(f"🔄 복구됨(Re-attached): [{ch_id}] PID={pid} ({manager.session_channel_name})")
            except psutil.NoSuchProcess:
                pass

    def __init__(self, channel_id: str):
        self.channel_id = channel_id
        import subprocess
        self.process: Optional[subprocess.Popen] = None
        self.is_recording = False
        self.output_path = ""
        
        # 세션(연속 방송 연속성) 관리용 보조 변수
        self.session_started_at = None
        self.session_part = 0
        self.session_platform = ""
        self.session_channel_name = ""
        self.session_title = ""
        self.session_category = ""
        self.session_record_type = "scheduled"

    def _reset_session_state(self):
        """세션 관련 상태를 모두 초기화합니다."""
        from app.services.session_manager import SessionManager
        SessionManager.end_session(self.channel_id)
        from app.utils.process_state import unregister_process
        unregister_process(self.channel_id)
        self.session_started_at = None
        self.session_part = 0
        self.session_title = ""
        self.session_category = ""
        self.output_path = ""

    async def start_record(self, cmd: list, output_path: str, channel_name: str, record_type: str = "scheduled"):
        """ FFmpeg 혹은 streamlink 프로세스를 실행 """
        if self.is_recording:
            logger.warning(f"[{channel_name}] 이미 녹화 중입니다.")
            return

        self.output_path = output_path
        self.is_recording = True
        self.session_record_type = record_type

        logger.info(f"[{channel_name}] 녹화 프로세스 시작: {' '.join(shlex.quote(x) for x in cmd)}")
        await send_telegram_message(f"<b>{channel_name}</b> 채널 라이브 감지. 녹화를 시작합니다.")
        await broadcast_event("recording_started", {
            "id": self.channel_id,
            "platform": self.session_platform,
            "name": channel_name,
            "record_type": record_type
        })

        try:
            import subprocess
            # uvicorn + asyncio 환경에서 Windows SelectorEventLoop 에러(NotImplementedError)를 회피하기 위해
            # 표준 subprocess.Popen 과 asyncio.to_thread 조합을 사용합니다.
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
            
            # 프로세스 재시작(Live Reload)을 견디기 위한 PID 디스크 저장
            meta_info = {
                "platform": self.session_platform,
                "name": channel_name,
                "title": self.session_title,
                "record_type": self.session_record_type,
                "output_path": self.output_path,
                "part": self.session_part
            }
            register_process(self.channel_id, self.process.pid, meta_info)
            
            # 프로세스 블로킹 대기를 비동기 스레드로 넘김
            def _wait_proc():
                _, stderr_output = self.process.communicate()
                return self.process.returncode, stderr_output
                
            returncode, stderr_bytes = await asyncio.to_thread(_wait_proc)

            # 정상 종료든, 에러든 여기까지 오면 종료된 것임
            logger.info(f"[{channel_name}] 녹화 프로세스 종료됨. Return Code: {returncode}")
            if returncode != 0 and stderr_bytes:
                stderr_text = stderr_bytes.decode('utf-8', errors='replace')[-1000:]
                logger.warning(f"[{channel_name}] 프로세스 stderr: {stderr_text}")

            # 후처리 디스패치 (Strategy 패턴 — post_processing.py에 위임)
            from app.services.post_processing import dispatch_post_processing
            await dispatch_post_processing(
                output_path=self.output_path,
                channel_name=channel_name,
                platform=self.session_platform,
                session_part=self.session_part,
            )
            
        except asyncio.CancelledError:
            logger.info(f"[{channel_name}] 강제 종료(Cancelled) 요청 받음.")
            
        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            logger.error(f"[{channel_name}] 프로세스 실행 중 예외: {e}\n{tb_str}")
            await send_error_alert(channel_name, "레코딩 프로세스(FFmpeg/Streamlink) 루프", str(e))
        finally:
            self.is_recording = False
            self.process = None
            self._reset_session_state()
            await broadcast_event("recording_stopped", {
                "id": self.channel_id,
                "name": channel_name
            })

    async def stop_record(self, channel_name: str):
        """ 실행 중인 FFmpeg 프로세스 강제 종료 """
        if not self.is_recording or not self.process:
            logger.warning(f"[{channel_name}] 녹화 중이 아닙니다.")
            return

        logger.info(f"[{channel_name}] 녹화 프로세스 중지 요청")
        self.process.terminate()
        
        def _wait_kill():
            try:
                self.process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
                
        await asyncio.to_thread(_wait_kill)

        logger.info(f"[{channel_name}] 프로세스 강제 완전 종료")
