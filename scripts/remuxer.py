import os
import sys
import time
import signal
import logging
import subprocess
import threading
import queue
from pathlib import Path
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler

# 환경변수 로딩
class RemuxConfig:
    WATCH_DIR = os.environ.get("REMUX_WATCH_DIR", "/app/output")
    CONCURRENCY = int(os.environ.get("REMUX_CONCURRENCY", "2"))
    RETRY_DELAY = int(os.environ.get("REMUX_RETRY_DELAY", "300"))
    STABLE_CHECK = int(os.environ.get("REMUX_STABLE_CHECK", "30"))
    MIN_SIZE = int(os.environ.get("REMUX_MIN_SIZE", "1024"))

# [2026-04-05 13:00:00] [INFO] [remuxer] 형식의 로깅 설정
logger = logging.getLogger("remuxer")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [remuxer] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)

class RemuxWorker:
    def __init__(self, config: RemuxConfig):
        self.config = config
        self.semaphore = threading.Semaphore(self.config.CONCURRENCY)
        self.retry_queue = queue.Queue()
        self.running = True
        self.processing_files = set() # 동시 처리 중복 방지
        self.lock = threading.Lock()

    def is_remuxed(self, ts_path: str) -> bool:
        mp4_path = ts_path[:-3] + ".mp4"
        return os.path.exists(mp4_path)

    def is_valid_target(self, filepath: str) -> bool:
        base = os.path.basename(filepath)
        if not base.endswith(".ts"):
            return False
        if "_part" in base:
            return False
        if "fixed_" in base:
            return False
        return True

    def wait_stable(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        init_size = os.path.getsize(path)
        time.sleep(self.config.STABLE_CHECK)
        if not os.path.exists(path):
            return False
        new_size = os.path.getsize(path)
        
        while init_size != new_size:
            init_size = new_size
            time.sleep(self.config.STABLE_CHECK)
            if not os.path.exists(path):
                return False
            new_size = os.path.getsize(path)
            if not self.running:
                return False
        return True

    def remux(self, ts_path: str) -> bool:
        mp4_path = ts_path[:-3] + ".mp4"
        try:
            file_size = os.path.getsize(ts_path)
        except OSError:
            logger.error(f"파일을 찾을 수 없음: {ts_path}")
            return False

        if file_size < self.config.MIN_SIZE:
            logger.warning(f"파일이 너무 작아 리먹싱 스킵 (크기: {file_size}): {ts_path}")
            return False

        # 파일 크기에 비례한 동적 타임아웃 (GB당 120초 + 기본 300초)
        # 예시: 1GB=420초, 10GB=1500초(25분), 20GB=2700초(45분), 30GB=3900초(65분)
        file_size_gb = file_size / (1024 * 1024 * 1024)
        timeout = 300 + int(file_size_gb * 120)

        logger.info(f"리먹싱 시작: {ts_path}")
        cmd = [
            "ffmpeg", "-y", "-nostdin",
            "-i", ts_path,
            "-c:v", "copy", "-c:a", "copy",
            "-movflags", "+faststart",
            mp4_path
        ]

        try:
            proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=timeout)
            if proc.returncode == 0:
                mp4_size = os.path.getsize(mp4_path) if os.path.exists(mp4_path) else 0
                if mp4_size >= self.config.MIN_SIZE:
                    logger.info(f"리먹싱 성공 ({mp4_size // (1024*1024)}MB): {mp4_path}")
                    try:
                        os.remove(ts_path)
                        logger.info(f"원본 삭제: {ts_path}")
                    except Exception as e:
                        logger.warning(f"원본 삭제 실패 {ts_path}: {e}")
                    return True
                else:
                    logger.error(f"결과 파일 크기 미달 ({mp4_size}B). 원본 유지: {ts_path}")
                    if os.path.exists(mp4_path):
                        os.remove(mp4_path)
            else:
                err_text = proc.stderr.decode('utf-8', errors='replace')[-500:]
                logger.error(f"리먹싱 실패 (Code: {proc.returncode})\nStderr: {err_text}")
        except subprocess.TimeoutExpired:
            logger.error(f"리먹싱 타임아웃 ({timeout}초 초과): {ts_path}")
        except Exception as e:
            logger.error(f"리먹싱 실행 중 예외: {str(e)}")

        return False

    def process(self, ts_path: str):
        if not self.running:
            return
            
        if not self.is_valid_target(ts_path) or self.is_remuxed(ts_path):
            self._clear_processing(ts_path)
            return
            
        if self.wait_stable(ts_path):
            with self.semaphore:
                if self.running:
                    success = self.remux(ts_path)
                    if not success and self.running:
                        logger.warning(f"리먹싱을 다시 시도하기 위해 큐에 추가: {ts_path}")
                        self.retry_queue.put((time.time() + self.config.RETRY_DELAY, ts_path))
                        
        self._clear_processing(ts_path)
        
    def _clear_processing(self, ts_path: str):
        with self.lock:
            if ts_path in self.processing_files:
                self.processing_files.remove(ts_path)

    def submit(self, ts_path: str):
        with self.lock:
            if ts_path in self.processing_files:
                return
            self.processing_files.add(ts_path)
            
        t = threading.Thread(target=self.process, args=(ts_path,), daemon=True)
        t.start()

    def scan_existing(self):
        logger.info(f"기존 .ts 파일 스캔 시작: {self.config.WATCH_DIR}")
        for filepath in Path(self.config.WATCH_DIR).rglob("*.ts"):
            path_str = str(filepath)
            if self.is_valid_target(path_str) and not self.is_remuxed(path_str):
                self.submit(path_str)

    def retry_loop(self):
        logger.info("재시도(Retry) 워커 루프 시작")
        pending = []
        while self.running:
            try:
                while True:
                    pending.append(self.retry_queue.get_nowait())
            except queue.Empty:
                pass
            
            now = time.time()
            to_process = [item for item in pending if now >= item[0]]
            pending = [item for item in pending if now < item[0]]
            
            for _, ts_path in to_process:
                self.submit(ts_path)
                
            time.sleep(5)

class TsFileHandler(FileSystemEventHandler):
    def __init__(self, worker: RemuxWorker):
        self.worker = worker

    def on_created(self, event):
        if event.is_directory:
            return
        if self.worker.is_valid_target(event.src_path):
            self.worker.submit(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        if self.worker.is_valid_target(event.src_path):
            # 파일이 커지는 중이면 이미 wait_stable 등에서 처리중이거나
            # 새롭게 수정된 경우 큐에 submit 하여 처리되도록 유도 (중복방지됨)
            self.worker.submit(event.src_path)

def main():
    config = RemuxConfig()
    
    if not os.path.exists(config.WATCH_DIR):
        os.makedirs(config.WATCH_DIR, exist_ok=True)
        
    worker = RemuxWorker(config)
    
    def signal_handler(signum, frame):
        logger.info("SIGTERM/SIGINT 수신. 리먹서 종료 중...")
        worker.running = False
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    worker.scan_existing()
    
    threading.Thread(target=worker.retry_loop, daemon=True).start()

    handler = TsFileHandler(worker)
    observer = Observer()
    observer.schedule(handler, path=config.WATCH_DIR, recursive=True)
    observer.start()
    
    logger.info(f"워치독(Watchdog) 시작됨: {config.WATCH_DIR} 하위를 감시합니다.")
    
    try:
        while observer.is_alive() and worker.running:
            observer.join(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
