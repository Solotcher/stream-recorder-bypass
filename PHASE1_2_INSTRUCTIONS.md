# Phase 1~2 개선 작업 지시서

> **작성**: Claude Opus 4.6 | **대상 실행 모델**: Gemini 3.1 Pro  
> **작업 완료 후**: `work_log.md`에 각 Step 완료 기록 필수

---

## ⚠️ 작업 전 필독

1. 이 지시서는 **순서대로 Step을 실행**하도록 설계되어 있습니다.
2. 각 Step에 **대상 파일**, **수정 위치**, **수정 내용**이 명시되어 있습니다.
3. 기존 코드의 다른 부분은 **절대 변경하지 마세요**.
4. 각 Step 완료 후 반드시 `work_log.md` 상단에 작업 기록을 추가하세요.

---

## Phase 1: 즉시 수정 (성능/기능)

---

### Step 1-1: TikTok yt-dlp 이중 호출 제거 (캐싱)

**대상 파일**: `app/extractors/tiktok.py`

**문제**: `scheduler.py`의 `check_all_channels()`에서 `is_live()` → `get_metadata()` 순서로 호출하는데, 둘 다 내부적으로 `_extract_with_ytdlp()`를 호출합니다. yt-dlp TikTok 추출은 5~10초 걸리므로 불필요한 API 부하가 2배입니다.

**수정 내용**:

1. `__init__` 메서드에 `self._cached_info = None` 추가 (기존 `self.stream_url = None` 바로 아래)

2. `is_live()` 메서드를 다음과 같이 수정:
```python
async def is_live(self) -> bool:
    """TikTok 라이브 방송 중인지 확인합니다."""
    self._cached_info = await self._extract_with_ytdlp()
    if self._cached_info and self._cached_info.get("is_live"):
        self.stream_url = self._cached_info.get("url")
        return True
    self._cached_info = None
    return False
```

3. `get_metadata()` 메서드의 첫 2줄을 다음으로 교체:
```python
async def get_metadata(self) -> Dict[str, Any]:
    """TikTok 라이브 스트림 메타데이터를 반환합니다."""
    info = self._cached_info or await self._extract_with_ytdlp()
    self._cached_info = None  # 사용 후 초기화
    if not info or not info.get("is_live"):
        return {"status": "CLOSE", "channel_name": self.channel_id}
    # 이하 기존 코드 유지 (self.stream_url = info.get("url") ...)
```

**주의**: `get_metadata()` 내부의 나머지 코드(return 딕셔너리 부분)는 그대로 유지합니다.

---

### Step 1-2: Kick yt-dlp 이중 호출 제거 (캐싱)

**대상 파일**: `app/extractors/kick.py`

**문제**: TikTok과 동일. `is_live()` + `get_metadata()` 에서 `_extract_with_ytdlp()` 2회 호출.

**수정 내용**:

1. `__init__` 메서드에 `self._cached_info = None` 추가:
```python
def __init__(self, channel_id: str, cookies: Optional[Dict[str, str]] = None):
    super().__init__(channel_id, cookies)
    self._cached_info = None
```

2. `is_live()` 메서드를 다음으로 교체:
```python
async def is_live(self) -> bool:
    self._cached_info = await self._extract_with_ytdlp()
    if self._cached_info and self._cached_info.get("is_live"):
        return True
    self._cached_info = None
    return False
```

3. `get_metadata()` 메서드의 첫 2줄을 다음으로 교체:
```python
async def get_metadata(self) -> Dict[str, Any]:
    info = self._cached_info or await self._extract_with_ytdlp()
    self._cached_info = None  # 사용 후 초기화
    if not info or not info.get("is_live"):
        return {"status": "CLOSE", "channel_name": self.channel_id}
    # 이하 기존 return 딕셔너리 코드 유지
```

**주의**: `get_metadata()` 내부의 return 딕셔너리 부분(status, title, channel_name, stream_url 등)은 그대로 유지합니다.

---

### Step 1-3: tasks.py VOD 다운로더 범용화 적용

**대상 파일**: `app/worker/tasks.py`

**문제**: `vod_downloader.py`는 이미 멀티플랫폼 범용화가 완료됐는데, Celery 경로의 `download_vod_celery_task()`는 YouTube 전용 하드코딩이 남아있음.

**수정 내용**: `download_vod_celery_task` 함수 전체를 다음으로 교체:

```python
@shared_task(name="tasks.download_vod")
def download_vod_celery_task(url: str, output_dir: str = settings.OUTPUT_DIR):
    """VOD 다운로드 Celery Task. vod_downloader의 범용 빌더를 재사용합니다."""
    from app.services.vod_downloader import _detect_platform, _build_vod_command

    platform = _detect_platform(url)
    logger.info(f"[Celery] {platform} VOD 다운로드 시작: {url}")
    _sync_send_telegram(f"🎬 <b>{platform} VOD 다운로드 시작</b>\n- URL: {url}")

    cmd = _build_vod_command(url, output_dir, platform)

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        if proc.returncode == 0:
            logger.info(f"[Celery] {platform} VOD 다운로드 완료: {url}")
            _sync_send_telegram(f"✅ <b>VOD 다운로드 완료</b>\n- URL: {url}\n서버 내 VOD 폴더에 저장되었습니다.")
        else:
            logger.error(f"[Celery] {platform} VOD 다운로드 실패. Code: {proc.returncode}\n{proc.stderr[-1000:]}")
            _sync_send_telegram(f"❌ <b>VOD 다운로드 에러</b>\n- URL: {url}\n다운로드 도중 에러가 발생했습니다.")
    except Exception as e:
        logger.error(f"[Celery] VOD 다운로드 예외 발생: {e}")
        _sync_send_telegram(f"❌ <b>VOD 다운로드 예외 발생</b>\n- URL: {url}\n원인: {str(e)}")
```

**주의**: 기존 `import os`와 `import subprocess`는 파일 상단에 이미 있으므로 추가 import 불필요. `_sync_send_telegram` 함수도 이미 같은 파일에 존재합니다.

---

### Step 1-4: Chzzk aiohttp 세션 누수 수정

**대상 파일**: `app/extractors/chzzk.py`

**문제**: 매 API 호출마다 `aiohttp.ClientSession()`을 새로 생성. `base_extractor.py`의 공유 세션(`_fetch_json`)을 사용해야 합니다.

**수정 내용**:

1. 파일 상단의 `import aiohttp` 는 삭제해도 되지만 남겨둬도 무방합니다.

2. `get_metadata()` 메서드를 다음으로 교체:
```python
async def get_metadata(self) -> Dict[str, Any]:
    url = self.BASE_API_URL.format(self.channel_id)
    
    try:
        data = await self._fetch_json(url, method="GET", timeout=10)
        if not data:
            return {"status": "CLOSE", "channel_name": self.channel_id}
        
        content = data.get("content", {})
        if not content:
            return {"status": "CLOSE"}
            
        status = content.get("status", "CLOSE")
        title = content.get("liveTitle", "제목 없음")
        thumbnail = content.get("liveImageUrl", "")
        category = content.get("liveCategoryValue", "")
        
        channel_name = self.channel_id
        try:
            info = await self.get_channel_info()
            channel_name = info.get("channel_name", self.channel_id)
        except Exception:
            pass
        
        return {
            "title": title,
            "channel_name": channel_name,
            "category": category,
            "status": status, 
            "thumbnail": thumbnail,
            "stream_url": f"https://chzzk.naver.com/live/{self.channel_id}"
        }
    except Exception as e:
        logger.error(f"Chzzk API 통신 실패: {str(e)}")
        
    return {"status": "CLOSE", "channel_name": self.channel_id}
```

3. `get_channel_info()` 메서드를 다음으로 교체:
```python
async def get_channel_info(self) -> Dict[str, Any]:
    """ 치지직 채널 고유 정보(닉네임 등) 조회 """
    url = f"https://api.chzzk.naver.com/service/v1/channels/{self.channel_id}"
    try:
        data = await self._fetch_json(url, method="GET", timeout=10)
        if data:
            content = data.get("content", {})
            if content:
                return {
                    "channel_name": content.get("channelName", self.channel_id),
                    "thumbnail": content.get("channelImageUrl", "")
                }
    except Exception as e:
        logger.error(f"Chzzk Channel API 통신 실패: {str(e)}")
        
    return {"channel_name": self.channel_id}
```

---

### Step 1-5: SOOP aiohttp 세션 누수 수정

**대상 파일**: `app/extractors/soop.py`

**문제**: Chzzk과 동일. 매 호출마다 새 세션 생성. 다만 SOOP은 POST 요청 + 커스텀 헤더(Origin, Referer)가 필요합니다.

**수정 내용**:

1. `get_metadata()` 메서드를 다음으로 교체:
```python
async def get_metadata(self) -> Dict[str, Any]:
    """ SOOP 방송국 정보 API를 통한 메타데이터 조회 """
    url = self.BASE_API_URL
    
    try:
        req_headers = self.headers.copy()
        req_headers["Origin"] = "https://play.sooplive.co.kr"
        req_headers["Referer"] = "https://play.sooplive.co.kr/"
        req_headers["Content-Type"] = "application/x-www-form-urlencoded"
        
        payload = f"bid={self.channel_id}"
        
        data = await self._fetch_json(url, method="POST", headers=req_headers, data=payload, timeout=10)
        
        if not data:
            logger.warning(f"SOOP API 응답 없음: {self.channel_id}")
            return {"status": "ERROR"}
        
        channel = data.get("CHANNEL")
        
        if not channel:
            logger.warning(f"SOOP API CHANNEL 응답 누락: {self.channel_id}")
            return {"status": "ERROR"}
            
        is_live = (channel.get("RESULT") == 1)
        
        if not is_live:
            return {"status": "CLOSE"}
            
        return {
            "title": channel.get("TITLE", "제목 없음"),
            "channel_name": channel.get("BJNICK", self.channel_id),
            "category": channel.get("CATE", ""),
            "status": "OPEN", 
            "stream_url": f"https://play.sooplive.co.kr/{self.channel_id}"
        }
    except Exception as e:
        logger.error(f"SOOP API 통신 실패: {str(e)}")
        return {"status": "ERROR"}
```

**주의**: `_fetch_json()`은 `base_extractor.py`에서 status 200이 아니면 빈 dict `{}`를 반환합니다. 또한 `content_type=None` 옵션이 필요한데, 현재 `_fetch_json()`은 `response.json()`을 그대로 호출합니다. SOOP API는 `text/html` MIME으로 JSON을 보내므로, `_fetch_json` 내부에서 `content_type=None`을 지원하도록 수정이 필요할 수 있습니다.

**추가 수정 필요** — `app/extractors/base_extractor.py`의 `_fetch_json()` 메서드 L81:

```python
# 변경 전:
return await response.json()

# 변경 후:
return await response.json(content_type=None)
```

이렇게 하면 SOOP처럼 Content-Type이 올바르지 않은 API 응답도 파싱할 수 있습니다. 치지직/인스타 등 기존 JSON API에는 영향 없습니다.

2. `get_channel_info()` 메서드를 다음으로 교체:
```python
async def get_channel_info(self) -> Dict[str, Any]:
    """ SOOP 플레이어 API를 재활용하여 라이브 관계없이 닉네임 파싱 시도 """
    url = self.BASE_API_URL
    try:
        req_headers = self.headers.copy()
        req_headers["Origin"] = "https://play.sooplive.co.kr"
        req_headers["Referer"] = "https://play.sooplive.co.kr/"
        req_headers["Content-Type"] = "application/x-www-form-urlencoded"
        
        payload = f"bid={self.channel_id}"
        
        data = await self._fetch_json(url, method="POST", headers=req_headers, data=payload, timeout=10)
        if data:
            channel = data.get("CHANNEL")
            if channel:
                return {"channel_name": channel.get("BJNICK", self.channel_id)}
    except Exception as e:
        logger.error(f"SOOP API 통신 실패 (채널조회): {str(e)}")
        
    return {"channel_name": self.channel_id}
```

3. 기존 `get_metadata()` 끝의 도달 불가능한 `return {"status": "ERROR", ...}` 줄 (현재 L61 근처)은 새 코드에서는 없어도 됩니다.

4. 파일 상단의 `import aiohttp`는 다른 곳에서 사용하지 않으므로 **삭제 가능**합니다. 다만 `is_live()`에서 `aiohttp`를 import하지 않으므로 삭제해도 안전합니다.

---

### Step 1-6: 프론트엔드 Kick/Instagram 선택지 추가

**대상 파일**: `frontend/index.html`

**수정 위치 1** — 수동 녹화 플랫폼 드롭다운 (`id="manual_platform"`, 현재 L46~53 부근):

`<option value="tiktok">틱톡</option>` 바로 아래에 다음 2줄 추가:
```html
<option value="kick">킥 (Kick)</option>
<option value="instagram">인스타그램 (Instagram)</option>
```

**수정 위치 2** — 채널 등록 모달 드롭다운 (`id="modal_platform"`, 현재 L127~134 부근):

`<option value="tiktok">틱톡 (TikTok)</option>` 바로 아래에 다음 2줄 추가:
```html
<option value="kick">킥 (Kick)</option>
<option value="instagram">인스타그램 (Instagram)</option>
```

---

### Step 1-7: Docker Healthcheck 추가

**대상 파일 1**: `Dockerfile`

`EXPOSE 8000` 줄 바로 아래에 다음 추가:
```dockerfile
# 컨테이너 헬스 체크 (30초 간격으로 /api/health 확인)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1
```

**대상 파일 2**: `app/api/` 디렉토리에 health 엔드포인트 추가

기존 라우터 중 가장 적합한 위치는 `app/api/config_routes.py` 또는 별도의 `app/api/health.py`입니다.

**가장 간단한 방법** — `app/api/config_routes.py` 파일에 다음 엔드포인트 추가:
```python
@router.get("/health")
async def health_check():
    """Docker 및 로드밸런서용 헬스 체크 엔드포인트"""
    return {"status": "ok", "version": settings.VERSION}
```

상단에 `from app.core.config import settings`가 이미 import되어 있는지 확인하고, 없으면 추가하세요.

---

## Phase 2: 안정성 강화

---

### Step 2-1: SessionManager 영속화

**대상 파일 1**: `app/db/models.py`

기존 `Channel` 모델 아래에 다음 모델 추가:
```python
class ActiveSession(Base):
    __tablename__ = "active_sessions"
    
    channel_id = Column(String, primary_key=True)
    platform = Column(String, nullable=False)
    channel_name = Column(String, nullable=False)
    title = Column(String, default="")
    category = Column(String, default="")
    record_type = Column(String, default="scheduled")
    started_at = Column(DateTime, nullable=True)
    part = Column(Integer, default=0)
```

`Column`, `String`, `Integer`, `DateTime` 등이 이미 import되어 있는지 확인하세요.

**대상 파일 2**: `app/services/session_manager.py`

`start_session()` 메서드 끝에 DB 저장 호출 추가:
```python
# start_session() 내부, return session 직전에 추가:
cls._persist_session(session)
```

`end_session()` 메서드 끝에 DB 삭제 호출 추가:
```python
# end_session() 내부, return 직전에 추가:
cls._remove_persisted_session(channel_id)
```

클래스에 다음 헬퍼 메서드 2개 추가:
```python
@classmethod
def _persist_session(cls, session: RecordingSession):
    """세션 상태를 DB에 저장합니다."""
    try:
        from app.db.session import SessionLocal
        from app.db.models import ActiveSession
        db = SessionLocal()
        try:
            record = db.query(ActiveSession).filter_by(channel_id=session.channel_id).first()
            if record:
                record.part = session.part
                record.title = session.title
                record.category = session.category
            else:
                record = ActiveSession(
                    channel_id=session.channel_id,
                    platform=session.platform,
                    channel_name=session.channel_name,
                    title=session.title,
                    category=session.category,
                    record_type=session.record_type,
                    started_at=session.started_at,
                    part=session.part,
                )
                db.add(record)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        from app.core.logger import logger
        logger.warning(f"세션 영속화 실패 (무시): {e}")

@classmethod
def _remove_persisted_session(cls, channel_id: str):
    """DB에서 세션 레코드를 삭제합니다."""
    try:
        from app.db.session import SessionLocal
        from app.db.models import ActiveSession
        db = SessionLocal()
        try:
            db.query(ActiveSession).filter_by(channel_id=channel_id).delete()
            db.commit()
        finally:
            db.close()
    except Exception as e:
        from app.core.logger import logger
        logger.warning(f"세션 삭제 실패 (무시): {e}")

@classmethod
def restore_all_sessions(cls):
    """서버 재시작 시 DB에서 세션을 복구합니다."""
    try:
        from app.db.session import SessionLocal
        from app.db.models import ActiveSession
        db = SessionLocal()
        try:
            records = db.query(ActiveSession).all()
            for r in records:
                cls._sessions[r.channel_id] = RecordingSession(
                    channel_id=r.channel_id,
                    platform=r.platform,
                    channel_name=r.channel_name,
                    title=r.title,
                    category=r.category,
                    record_type=r.record_type,
                    started_at=r.started_at,
                    part=r.part,
                )
            if records:
                from app.core.logger import logger
                logger.info(f"🔄 {len(records)}개 세션 DB에서 복구 완료")
        finally:
            db.close()
    except Exception as e:
        from app.core.logger import logger
        logger.warning(f"세션 복구 실패 (무시): {e}")
```

**대상 파일 3**: `app/main.py`

`lifespan()` 함수 내 `RecorderManager.restore_active_processes()` 바로 아래에 추가:
```python
from app.services.session_manager import SessionManager
try:
    SessionManager.restore_all_sessions()
except Exception as e:
    logger.error(f"세션 복구 실패: {e}")
```

---

### Step 2-2: dependency_manager 비동기화

**대상 파일 1**: `app/utils/dependency_manager.py`

`ensure_streamlink()` 내부의 pip upgrade 부분을 별도 함수로 분리:
```python
def _background_update_streamlink():
    """백그라운드에서 streamlink 업데이트 시도 (실패해도 무시)"""
    import subprocess
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "streamlink", "--quiet"], check=False)
        logger.info("🎉 Streamlink 업데이트 체크 완료.")
    except Exception as e:
        logger.warning(f"⚠️ Streamlink 업데이트 실패 (무시됨): {e}")

def _background_update_ytdlp(path: str):
    """백그라운드에서 yt-dlp 업데이트 시도 (실패해도 무시)"""
    import subprocess
    try:
        subprocess.run([path, "-U"], capture_output=True, text=True, check=False)
        logger.info("🎉 yt-dlp 업데이트 체크 완료.")
    except Exception as e:
        logger.warning(f"⚠️ yt-dlp 업데이트 실패 (무시됨): {e}")
```

`ensure_streamlink()`과 `ensure_ytdlp()`에서 기존의 인라인 업데이트 코드를 제거하고, 경로만 반환하도록 수정.

`check_all_dependencies()` 끝에 비동기 업데이트 런처 함수 추가:
```python
def schedule_background_updates():
    """서버 시작 후 백그라운드에서 의존성 업데이트를 수행합니다."""
    import threading
    threading.Thread(target=_background_update_streamlink, daemon=True).start()
    if settings.YTDLP_PATH and settings.YTDLP_PATH != "yt-dlp":
        threading.Thread(target=_background_update_ytdlp, args=(settings.YTDLP_PATH,), daemon=True).start()
```

**대상 파일 2**: `app/main.py`

`lifespan()` 내 `check_all_dependencies()` 호출 바로 아래에 추가:
```python
from app.utils.dependency_manager import schedule_background_updates
schedule_background_updates()
```

---

### Step 2-3: 보안 강화 (CORS + 에러 메시지)

**대상 파일 1**: `app/core/config.py`

`Settings` 클래스 내부에 추가:
```python
# CORS 허용 도메인 (쉼표 구분, 기본 전체 허용)
ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "*")
```

**대상 파일 2**: `app/main.py`

1. CORS 설정 부분 (현재 L63 부근)을 다음으로 교체:
```python
# CORS: 환경변수로 제어 (기본값 *, 운영 시 도메인 지정 권장)
raw_origins = settings.ALLOWED_ORIGINS
if raw_origins.strip() == "*":
    allowed_origins = ["*"]
else:
    allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
```

2. 전역 예외 핸들러 (현재 L99~110 부근)에서 메시지 부분을 수정:
```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    err_msg = str(exc)
    logger.error(f"[Trace: {trace_id.get()}] 전역 예외 발생: {err_msg}")
    # 운영 환경에서는 내부 에러 상세 숨김
    display_message = err_msg if settings.DEBUG else "내부 서버 오류가 발생했습니다."
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_SERVER_ERROR",
            "message": display_message,
            "traceId": trace_id.get()
        }
    )
```

---

## 작업 완료 체크리스트

- [ ] Step 1-1: TikTok 캐싱 적용
- [ ] Step 1-2: Kick 캐싱 적용
- [ ] Step 1-3: tasks.py VOD 범용화
- [ ] Step 1-4: Chzzk aiohttp 세션 통합
- [ ] Step 1-5: SOOP aiohttp 세션 통합 + base_extractor content_type 수정
- [ ] Step 1-6: 프론트엔드 Kick/Instagram 추가
- [ ] Step 1-7: Docker Healthcheck
- [ ] Step 2-1: SessionManager 영속화
- [ ] Step 2-2: dependency_manager 비동기화
- [ ] Step 2-3: 보안 강화
- [ ] work_log.md 기록 완료
- [ ] Git 커밋 & 푸시

---

## 작업 완료 후

Phase 1~2 전체 완료 후 **Claude Opus 모델로 전환**하여 교차 리뷰를 요청하세요.
프롬프트 예시: "3.1 프로가 Phase 1~2 작업 끝냈는데 리뷰해줘"
