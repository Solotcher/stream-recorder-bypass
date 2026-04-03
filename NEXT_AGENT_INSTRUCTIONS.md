# 🤖 AI 에이전트 작업 지침서 (Next Agent Instructions)

> **최종 갱신**: 2026-03-25 06:45 KST | **작성 모델**: Antigravity (Claude 4 Sonnet)  
> **이 파일의 목적**: 다음 세션에서 어떤 AI 모델이든 이 파일을 읽고 바로 작업을 시작할 수 있도록 하는 **자기 완결형 작업 지침서**입니다.

---

## ⚠️ 필수 사전 규칙 (반드시 먼저 읽을 것)

1. **모든 작업은 `work_log.md`에 기록** (형식은 기존 로그 참조)
2. **한국어로 응답 및 기록** (기술 용어만 영어 허용)
3. **MCP 도구를 통해서만 파일 수정** (직접 수정 금지)
4. **함수는 25줄 이내** / **중첩 조건문 2단계 이내** (Clean Code 가이드라인)

---

## 📋 프로젝트 현황 요약

| 항목 | 내용 |
|------|------|
| **프로젝트** | Stream Recorder — 6개 플랫폼 자동 녹화 웹앱 |
| **백엔드** | FastAPI + APScheduler + SQLite(SQLAlchemy) + Celery+Redis |
| **프론트엔드** | Vanilla JS SPA (ES Modules) |
| **배포** | Docker Compose 3컨테이너 (app, redis, celery_worker) |
| **지원 플랫폼** | 치지직, SOOP, 트위치, 유튜브, 틱톡, 인스타그램, Kick |

### 핵심 파일 맵 (빠른 탐색용)

```
app/
├── main.py                  ← FastAPI 엔트리포인트 (lifespan, 미들웨어, WebSocket)
├── core/config.py           ← 환경 설정 (Settings, .env 로딩)
├── core/logger.py           ← 로거 + Trace ID (ContextVar)
├── api/endpoints.py         ← REST API 전체 (280줄, 분할 예정)
├── db/session.py            ← SQLAlchemy 엔진/세션 팩토리
├── db/models.py             ← Channel ORM 모델
├── extractors/              ← 플랫폼별 추출기 (BaseExtractor ABC)
│   ├── base_extractor.py    ← 공통 추상 클래스 + aiohttp 세션 관리
│   ├── chzzk.py / soop.py / twitch.py / youtube.py / tiktok.py / instagram.py / kick.py
├── services/
│   ├── scheduler.py         ← APScheduler 30초 폴링 + trigger_recording (리팩토링 대상)
│   ├── recorder.py          ← RecorderManager (subprocess.Popen + asyncio.to_thread)
│   ├── merger.py            ← FFmpeg 리먹싱/병합 (헬퍼 함수 추출 완료)
│   ├── uploader.py          ← rclone 클라우드 업로드
│   └── vod_downloader.py    ← yt-dlp VOD 다운로드
├── worker/
│   ├── celery_app.py        ← Celery 브로커 설정
│   └── tasks.py             ← Celery Task (remuxing, concat, vod) ← merger와 DRY 위반 중
├── utils/
│   ├── channel_db.py        ← 채널 DB CRUD (Repository 이관 예정)
│   ├── cookie_manager.py    ← 쿠키 파싱/저장
│   ├── event_bus.py         ← WebSocket ConnectionManager
│   ├── process_state.py     ← PID 영속 저장/복구
│   ├── telegram_bot.py      ← 텔레그램 알림
│   └── dependency_manager.py← FFmpeg/yt-dlp/Streamlink 자동 설치
frontend/
├── index.html / style.css   ← SPA 레이아웃
├── script.js / api.js       ← 이벤트 델리게이션 + API 호출
├── config.js / ui.js / ws.js← 상수, UI 유틸, WebSocket 클라이언트
```

---

## 🎯 다음 작업: 6단계 리팩토링 로드맵

> **상세 명세, 코드 뼈대, Mermaid 다이어그램**은 아래 아키텍처 리뷰 문서를 참조하세요.  
> 여기서는 **즉시 실행 가능한 단계별 지시**만 제공합니다.

---

### Step 1: Command 모듈 신설 — `trigger_recording` God Function 분해 ⭐ 1순위

**목표**: scheduler.py의 90줄짜리 `trigger_recording()` 함수를 3개 책임 단위로 분리

**생성할 파일**:
- `app/commands/__init__.py`
- `app/commands/base.py` — `CommandBuilder` ABC (인터페이스)
- `app/commands/streamlink_builder.py` — 치지직/트위치/SOOP/인스타 커맨드 조립
- `app/commands/ytdlp_builder.py` — 유튜브/틱톡 커맨드 조립
- `app/commands/filename_generator.py` — FILENAME_PATTERN 기반 파일명 생성

**수정할 파일**:
- `app/services/scheduler.py` — `trigger_recording()`을 Builder/Generator 호출로 경량화

**핵심 로직 참조 위치**:
- 세션 관리: `scheduler.py` L62-71
- 파일명 생성: `scheduler.py` L73-111
- 커맨드 조립: `scheduler.py` L113-148 (platform별 분기)

**검증**: 기존 녹화 동작이 100% 동일하게 유지되어야 함

---

### Step 2: SessionManager 신설 — RecorderManager 경량화

**목표**: 녹화 세션 상태(started_at, part, platform, channel_name 등)를 전담 관리자로 분리

**생성할 파일**:
- `app/services/session_manager.py` — `RecordingSession` dataclass + `SessionManager` 싱글턴

**수정할 파일**:
- `app/services/recorder.py` — session_* 속성 6개 제거, SessionManager 참조
- `app/services/scheduler.py` — check_all_channels()에서 SessionManager 활용
- `app/api/endpoints.py` — `/records/active`에서 SessionManager 활용

---

### Step 3: endpoints.py 분할 (API 라우터 모듈화)

**목표**: 280줄 모놀리식 → 4개 기능별 파일로 분리

**생성할 파일**:
- `app/api/__init__.py` — include_router 통합
- `app/api/channels.py` — 채널 CRUD (`/channels`, `/channel/{id}/start`)
- `app/api/recordings.py` — 녹화 제어 (`/records/*`, `/channel/{id}/stop`)
- `app/api/settings.py` — 설정/쿠키 (`/config`, `/cookies/*`)
- `app/api/vod.py` — VOD 다운로드 (`/vod/download`)
- `app/api/schemas.py` — Pydantic 모델 통합

**주의**: API 경로(prefix)는 절대 변경하지 말 것

---

### Step 4: Repository 패턴 적용

**목표**: `channel_db.py`의 함수형 DB 접근 → `ChannelRepository` 클래스 캡슐화

**생성할 파일**:
- `app/repositories/__init__.py`
- `app/repositories/channel_repository.py`

**핵심**: FastAPI `Depends(get_db)`로 요청 단위 세션 관리

---

### Step 5: Event-Driven 후처리 (Optional, 고난이도)

**목표**: recorder.py의 후처리 직접 호출 → 이벤트 발행/구독으로 약한 결합

**생성할 파일**:
- `app/events/__init__.py`
- `app/events/types.py` — `RecordingFinishedEvent` 등 dataclass
- `app/events/handlers.py` — `RemuxingHandler`, `UploaderHandler`, `TelegramHandler`

**주의**: Step 1~4 완료 후 착수 권장 (파급력 가장 큼)

---

### Step 6: 리소스 정리 및 DRY 개선 (독립 작업, 즉시 가능)

**즉시 수행 가능한 작업 목록**:
1. `main.py` lifespan shutdown에 `_global_session.close()` 추가
2. `tasks.py`의 중복 FFmpeg 로직 → `merger.py` 동기 래퍼로 교체
3. `resolve_ffmpeg_path()` 중복 제거 (merger.py + tasks.py → 단일 함수)
4. `recorder.py` subprocess stderr를 `PIPE`로 변경하고 로그에 기록

---

## 🔧 개발 환경 셋업

```bash
# Docker 환경 (권장)
docker compose up -d --build

# 로컬 개발 (Windows)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**접속**: `http://localhost:8000`

---

## 📎 참조 문서

| 문서 | 위치 | 내용 |
|------|------|------|
| **아키텍처 리뷰** (상세 명세 포함) | 이전 세션 아티팩트 `architecture_review.md` | 강점/취약점 분석, Mermaid 다이어그램, 모듈별 인터페이스 뼈대, TODO 명세 |
| **작업 로그** | `work_log.md` | Phase 1~8 전체 이력 (908줄+) |
| **인수인계서** | `handover_document_for_next_agent.md` | 이전 세션 블로커 (대시보드 UI 렌더링 이슈 — 사용자가 직접 해결 완료) |

---

## ❗ 기존에 알려진 이슈

| # | 상태 | 내용 |
|---|------|------|
| 1 | ⚠️ 주의 | SOOP 녹화 로직 불안정 (세그먼트 처리 방식 미흡) |
| 2 | ✅ 해결됨 | 대시보드 h3 렌더링 누락 (사용자가 직접 해결) |
| 3 | ⚠️ 주의 | TestSprite 404 이슈 (API prefix `/api` 매칭 오류) |
| 4 | ⚠️ 주의 | `tasks.py` ↔ `merger.py` 코드 중복 (Step 6에서 해결 예정) |

---

## 🏗️ 작업 시작 프롬프트 예시

아래를 복사하여 다음 AI 모델에게 붙여넣으면 됩니다:

```
이 프로젝트의 NEXT_AGENT_INSTRUCTIONS.md 파일을 먼저 읽어줘.
그 다음 work_log.md를 확인하고,
Step [번호]부터 작업을 시작해줘.
MCP를 사용해서 진행하고, 작업 로그는 work_log.md에 기록해줘.
```
