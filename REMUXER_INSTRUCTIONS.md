# 리먹싱 전용 사이드카 컨테이너 구현 지침서

> **작성 일시**: 2026-04-05  
> **작성 모델**: Claude Opus 4.6 (Thinking)  
> **목적**: Docker 환경에서 간헐적 리먹싱 실패를 해결하기 위한 전용 컨테이너 도입  
> **난이도**: 중  
> **예상 소요**: 1~2시간

---

## 1. 배경 및 문제점

### 현재 아키텍처
```
docker-compose.yml 컨테이너 구성:
├── stream-recorder    (FastAPI + Streamlink 녹화 메인)
├── redis              (메시지 브로커)
└── celery_worker      (후처리 워커: 리먹싱 + SOOP concat + VOD 다운로드)
```

### 문제
- 녹화 완료 후 `.ts → .mp4` 리먹싱이 **가끔 실패**함
- 원본 `.ts` 파일은 정상이므로 다시 리먹싱하면 해결됨
- 서버에서 운영 시 실패할 때마다 직접 접속 → 명령어 실행 → 파일 다운로드 해야 해서 불편

### 해결 방안
- **output 디렉토리를 자동 감시**하는 리먹싱 전용 컨테이너 신설
- `.ts` 파일 발견 시 자동 리먹싱 → 실패 시 자동 재시도
- 서버 재시작 시에도 미처리 파일을 전체 스캔하여 누락분 보완

---

## 2. 변경할 파일 목록

| 작업 | 파일 경로 | 설명 |
|------|-----------|------|
| **신규** | `scripts/remuxer.py` | watchdog 기반 자동 리먹싱 워커 스크립트 |
| **신규** | `Dockerfile.remuxer` | 경량 전용 Docker 이미지 |
| **수정** | `docker-compose.yml` | remuxer 서비스 추가 |
| **수정** | `app/services/post_processing.py` | REMUXER_ENABLED 플래그 추가 |
| **수정** | `app/core/config.py` | REMUXER_ENABLED 설정 추가 |
| **기록** | `work_log.md` | 작업 로그 기록 |

---

## 3. 파일별 상세 구현 지침

---

### 3.1 [신규] `scripts/remuxer.py`

독립 실행 Python 스크립트. `watchdog` 라이브러리로 output 디렉토리를 감시하고, `.ts` 파일을 자동으로 `.mp4`로 리먹싱한다.

#### 핵심 동작 흐름
```
1. 시작 시 REMUX_WATCH_DIR(기본 /app/output) 하위 전체 스캔
   → 대응하는 .mp4가 없는 .ts 파일 발견 시 리먹싱 큐에 추가
2. watchdog Observer로 디렉토리 감시 시작
   → FileCreatedEvent 또는 FileModifiedEvent 중 .ts 확장자만 필터
3. 파일 안정화 대기: REMUX_STABLE_CHECK(기본 30초) 간격으로 2회 크기 체크
   → 크기가 변하지 않으면 쓰기 완료로 간주
4. FFmpeg 리먹싱 실행:
   ffmpeg -y -nostdin -i input.ts -c:v copy -c:a copy -movflags +faststart output.mp4
5. 결과 검증: .mp4 크기가 1KB 이상이면 성공 → 원본 .ts 삭제
6. 실패 시: 원본 보존, REMUX_RETRY_DELAY(기본 300초) 후 1회 재시도
```

#### 환경변수
```
REMUX_WATCH_DIR      = /app/output      (감시 대상 디렉토리)
REMUX_CONCURRENCY    = 2                (동시 리먹싱 제한)
REMUX_RETRY_DELAY    = 300              (실패 시 재시도 대기 초)
REMUX_STABLE_CHECK   = 30               (파일 안정화 체크 간격 초)
REMUX_MIN_SIZE       = 1024             (최소 유효 파일 크기 바이트)
```

#### 전체 코드 작성 요구사항

```python
# scripts/remuxer.py
"""
리먹싱 전용 Watcher.
output 디렉토리를 감시하여 .ts 파일을 .mp4로 자동 리먹싱합니다.
독립 실행 스크립트로, stream-recorder 앱과 무관하게 동작합니다.
"""
```

**필수 import**: `os, sys, time, signal, logging, subprocess, threading, queue`  
**외부 import**: `watchdog.observers.Observer`, `watchdog.events.FileSystemEventHandler`

**클래스 구조**:

1. `RemuxConfig` — 환경변수 로드 (dataclass 또는 단순 클래스)
2. `RemuxWorker` — 리먹싱 실행 워커
   - `__init__(self, config: RemuxConfig)` — 세마포어, 재시도 큐 초기화
   - `is_remuxed(self, ts_path: str) -> bool` — 대응 .mp4 존재 여부
   - `wait_stable(self, path: str) -> bool` — 크기 변동 없음 확인
   - `remux(self, ts_path: str) -> bool` — FFmpeg 실행 + 결과 검증
   - `process(self, ts_path: str)` — wait_stable → remux → 실패 시 재시도 큐
   - `scan_existing(self)` — 시작 시 기존 .ts 전체 스캔
   - `retry_loop(self)` — 재시도 큐 소비 (별도 스레드)
3. `TsFileHandler(FileSystemEventHandler)` — watchdog 이벤트 핸들러
   - `on_created(self, event)` — .ts 파일만 필터, 스레드풀에 process 제출
4. `main()` 함수
   - 로깅 설정 (JSON-like 포맷, stdout 출력)
   - SIGTERM/SIGINT 핸들링 (graceful shutdown)
   - Observer 시작 + retry_loop 스레드 시작
   - 메인 루프 (observer.is_alive() 체크)

**주의사항**:
- `_part` 키워드가 포함된 `.ts` 파일은 **스킵** (SOOP 파트 파일은 scheduler가 concat 후 처리)
- `.webm` 파일도 **스킵** (SOOP의 webm 조각은 별도 concat 처리됨)
- 하위 디렉토리 재귀 감시 필요 (`recursive=True`)
- 동시 처리는 `threading.Semaphore(REMUX_CONCURRENCY)`로 제한
- FFmpeg 타임아웃: 파일 크기에 비례 (기본 300초, 10GB 이상이면 600초)

**FFmpeg 명령어 정확한 형식**:
```bash
ffmpeg -y -nostdin -i "{input_path}" -c:v copy -c:a copy -movflags +faststart "{output_path}"
```

**로깅 형식**:
```
[2026-04-05 13:00:00] [INFO] [remuxer] 리먹싱 시작: /app/output/채널명/파일명.ts
[2026-04-05 13:00:03] [INFO] [remuxer] 리먹싱 성공 (1234MB): /app/output/채널명/파일명.mp4
[2026-04-05 13:00:03] [INFO] [remuxer] 원본 삭제: /app/output/채널명/파일명.ts
```

---

### 3.2 [신규] `Dockerfile.remuxer`

경량 이미지. FFmpeg + Python + watchdog만 포함.

```dockerfile
# FFmpeg 리먹싱 전용 경량 컨테이너
FROM python:3.14-slim

ENV TZ=Asia/Seoul
RUN apt-get update && apt-get install -y \
    ffmpeg \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

RUN pip install --no-cache-dir watchdog

COPY scripts/remuxer.py .

CMD ["python", "remuxer.py"]
```

> **참고**: 프로젝트 루트의 기존 `Dockerfile`은 수정하지 않음.

---

### 3.3 [수정] `docker-compose.yml`

기존 51줄의 끝에 `remuxer` 서비스를 추가한다.

**추가할 내용** (기존 `celery_worker` 서비스 아래에):

```yaml
  remuxer:
    build:
      context: .
      dockerfile: Dockerfile.remuxer
    container_name: stream-recorder-remuxer
    restart: unless-stopped
    volumes:
      - ./output:/app/output
    environment:
      - TZ=Asia/Seoul
      - REMUX_WATCH_DIR=/app/output
      - REMUX_CONCURRENCY=2
      - REMUX_RETRY_DELAY=300
      - REMUX_STABLE_CHECK=30
```

**주의**: 기존 서비스들은 절대 수정하지 않는다. 끝에 추가만 한다.

---

### 3.4 [수정] `app/core/config.py`

`Settings` 클래스에 환경변수 1줄 추가:

**추가 위치**: `FFMPEG_PATH` 설정 근처

```python
    REMUXER_ENABLED: bool = False  # True면 Celery 리먹싱 스킵 (remuxer 컨테이너가 처리)
```

---

### 3.5 [수정] `app/services/post_processing.py`

`RemuxingHandler.handle()` 메서드의 맨 앞에 early return 조건 추가:

**추가 위치**: `handle()` 메서드 본문 시작부 (line 49 이전)

```python
    async def handle(
        self,
        output_path: str,
        channel_name: str,
        platform: str,
        session_part: int = 0
    ) -> None:
        # remuxer 컨테이너가 활성화된 경우 Celery 리먹싱을 스킵
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

        # 기존 코드 (Celery 위임 + Fallback) 그대로 유지
        from app.worker.tasks import process_remuxing_celery_task
        # ... (이하 기존 코드 변경 없음)
```

**핵심**: 기존 로직을 삭제하지 말고, `if settings.REMUXER_ENABLED:` 가드만 앞에 추가한다.

---

### 3.6 [수정] `docker-compose.yml`의 stream-recorder 서비스

`REMUXER_ENABLED=true` 환경변수를 stream-recorder 서비스에 추가:

```yaml
    environment:
      - TZ=Asia/Seoul
      - REDIS_URL=redis://redis:6379/0
      - REMUXER_ENABLED=true    # ← 이 줄 추가
```

---

## 4. 파일 간 의존성 관계

```
remuxer.py (독립 스크립트, 프로젝트 코드 import 없음)
  ├── watchdog (pip 패키지)
  ├── ffmpeg (OS 패키지)
  └── output/ 볼륨 (docker-compose 마운트)

stream-recorder (기존 앱)
  └── post_processing.py
       └── settings.REMUXER_ENABLED == True 이면 Celery 리먹싱 스킵
```

> **중요**: `scripts/remuxer.py`는 프로젝트의 `app/` 패키지를 일절 import하지 않는다.  
> 완전히 독립적인 스크립트로 작성해야 한다. (텔레그램 알림, uploader 등 없음)

---

## 5. 스킵 조건 정리

remuxer.py가 **처리하지 않아야 할** 파일:

| 조건 | 이유 |
|------|------|
| `_part` 이 파일명에 포함 | SOOP 분할 파일. scheduler가 concat 후 처리 |
| `.webm` 확장자 | SOOP 녹화 포맷. concat 대상이지 리먹싱 대상 아님 |
| 이미 대응 `.mp4`가 존재 | 이미 처리 완료 |
| 파일 크기 < 1KB | 비정상 파일(빈 파일 등) |
| 파일 크기가 아직 변동 중 | 녹화가 진행 중인 파일 |

---

## 6. 검증 방법

### 자동 검증
```bash
# 1. 전체 컨테이너 빌드 & 기동
docker-compose up -d --build

# 2. 4개 컨테이너 기동 확인
docker ps  # stream-recorder-app, redis, celery, remuxer 4개 확인

# 3. remuxer 로그 확인 (초기 스캔 로그)
docker logs stream-recorder-remuxer

# 4. 테스트: output 디렉토리에 .ts 파일 복사
docker cp test_sample.ts stream-recorder-remuxer:/app/output/test/test_sample.ts

# 5. 30~60초 후 리먹싱 결과 확인
docker exec stream-recorder-remuxer ls -la /app/output/test/
# → test_sample.mp4가 생성되고, test_sample.ts가 삭제되어야 함

# 6. remuxer 로그에서 성공 메시지 확인
docker logs stream-recorder-remuxer --tail 20
```

### 수동 검증 (실제 녹화 테스트)
1. 치지직 스트림 녹화 시작 → 잠시 후 녹화 중지
2. `output/채널명/` 디렉토리에 `.ts` 파일 생성 확인
3. remuxer 컨테이너 로그에서 자동 리먹싱 시작/완료 메시지 확인
4. `.mp4` 생성 + `.ts` 삭제 확인
5. remuxer 컨테이너 재시작 후 미처리 파일 재스캔 확인

---

## 7. 주의사항 & 트러블슈팅

### 볼륨 권한 문제
- Docker 내부에서 FFmpeg가 output 디렉토리에 쓰기 권한이 있어야 함
- `./output:/app/output` 마운트이므로 호스트의 output 디렉토리 권한 확인

### 파일명 인코딩
- 한글 파일명(채널명, 방송 제목)이 포함되므로 UTF-8 인코딩 필수
- FFmpeg 인자에 한글 경로가 들어가도 문제없음 (Linux/Docker 기본 UTF-8)

### 동시 접근 충돌
- 녹화 중(.ts 파일이 계속 커지는 중)에 리먹싱을 시작하면 안 됨
- `wait_stable()` 함수에서 30초 간격 2회 크기 체크로 보호
- 파일 크기가 변동 중이면 리먹싱 큐에서 제외하고 다음 감시 이벤트를 기다림

### SOOP concat과의 충돌 방지
- `_part`가 포함된 파일은 절대 건드리지 않음
- concat이 완료되면 `_part` 없는 최종 `.ts` 파일이 생성됨 → 이것만 리먹싱

---

## 8. 작업 로그 기록 예시

작업 완료 후 `work_log.md`에 아래 형식으로 기록:

```
[2026-04-05 XX:XX:XX]
MODEL: (사용한 모델명)
MCP: (사용한 MCP)
TYPE: feature_add
TARGET: scripts/remuxer.py, Dockerfile.remuxer, docker-compose.yml, app/services/post_processing.py, app/core/config.py
DESCRIPTION: 리먹싱 전용 사이드카 컨테이너(remuxer) 도입. 1) scripts/remuxer.py — watchdog 기반 output 디렉토리 감시 + 자동 .ts→.mp4 리먹싱 독립 스크립트 신설. 2) Dockerfile.remuxer — FFmpeg+Python+watchdog 경량 전용 이미지. 3) docker-compose.yml에 remuxer 서비스 추가. 4) REMUXER_ENABLED 환경변수 플래그로 기존 Celery 리먹싱과 택일 가능하도록 post_processing.py 수정.
RESULT: (성공/실패)
```
