# 🔧 플랫폼 오작동 수정 작업 지시서 (Gemini 3.1 Pro 전용)

> **작성**: Antigravity (Claude Opus 4.6 Thinking) | **날짜**: 2026-04-03  
> **목적**: 이 파일을 읽고 Phase A → B → C 순서로 작업을 수행하세요.  
> **필수 규칙**: 모든 작업은 `work_log.md`에 기록, 한국어 작성, MCP 도구 사용

---

## ⚠️ 사전 준비

1. 이 파일을 먼저 끝까지 읽으세요.
2. `work_log.md`의 마지막 항목을 확인하여 현재 진행 상황을 파악하세요.
3. 각 Step 완료 후 반드시 `work_log.md`에 기록하세요.

---

## Phase A: 즉시 수정 (구조적 버그 4건)

### Step A1: Kick EXTRACTOR_MAP 등록

**파일**: `app/services/scheduler.py`

1. 상단 import에 추가:
```python
from app.extractors.kick import KickExtractor
```

2. `EXTRACTOR_MAP` 딕셔너리(L28-35)에 추가:
```python
"kick": KickExtractor,
```

---

### Step A2: KickExtractor stream_url 추가

**파일**: `app/extractors/kick.py`

`get_metadata()` 반환 딕셔너리에 `"stream_url"` 키 추가:
```python
"stream_url": f"https://kick.com/{self.channel_id}",
```

---

### Step A3: KickExtractor get_streamlink_args() 중복 제거

**파일**: `app/extractors/kick.py`

현재 `get_streamlink_args()`에 URL과 quality가 들어있어 `StreamlinkCommandBuilder`에서 중복됩니다.  
다음으로 교체:

```python
def get_streamlink_args(self) -> list:
    """Kick 녹화용 Streamlink 부가 인자. URL과 quality는 CommandBuilder에서 주입."""
    return [
        "--hls-live-restart",
        "--stream-timeout", "60",
        "--retry-streams", "5",
    ]
```

---

### Step A4: Phase A 검증

- 서버 기동 후 `EXTRACTOR_MAP`에 kick이 포함되는지 확인
- KickExtractor().get_metadata() 반환값에 stream_url 존재 확인
- 로그에 Kick 관련 커맨드가 URL 중복 없이 생성되는지 확인

---

## Phase B: 로직 개선 (4개 플랫폼 핵심 문제)

### Step B1: YouTube 라이브 — yt-dlp 인자 보강

**파일**: `app/extractors/youtube.py`

`get_streamlink_args()` (L139-156)에 라이브 전용 인자 추가:

```python
def get_streamlink_args(self) -> list:
    args = [
        "--no-part",
        "--no-playlist",
        "--socket-timeout", "15",
        "--retries", "10",
        "--fragment-retries", "10",
        # 라이브 전용
        "--live-from-start",
        "--wait-for-video", "30-120",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
        "--merge-output-format", "mp4",
    ]
    cookie_file = self._get_cookies_file_path()
    if cookie_file:
        args.extend(["--cookies", cookie_file])
    return args
```

**주의**: `--live-from-start`는 yt-dlp 2022.10.04+ 필요. `--wait-for-video`는 라이브 시작 대기용.

---

### Step B2: SOOP 녹화 안정화

**파일**: `app/extractors/soop.py`

`get_streamlink_args()` (L259-284)의 타임아웃/재시도 값을 강화:

```python
def get_streamlink_args(self) -> list:
    args = [
        "--ffmpeg-copyts",
        "--stream-segment-timeout", "30",   # 15→30
        "--stream-timeout", "120",          # 60→120
        "--retry-streams", "10",            # 5→10
        "--retry-open", "5",               # 3→5
        "--hls-live-restart",
        "--hls-segment-stream-data",
        "--http-header", "Origin=https://play.sooplive.co.kr",
        "--http-header", "Referer=https://play.sooplive.co.kr/"
    ]
    cookie_str = self.get_cookie_string()
    if cookie_str:
        args.extend(["--http-header", f"Cookie={cookie_str}"])
    stream_pw = getattr(self, "stream_password", None)
    if stream_pw:
        args.extend(["--soop-stream-password", stream_pw])
    return args
```

**추가 고려**: Streamlink 최신 버전에서 SOOP 플러그인이 개선되었는지 context7로 확인 후 반영.

---

### Step B3: TikTok — 쿠키 전달 체계 구축

**파일**: `app/extractors/tiktok.py`

1. 쿠키 파일 생성 메서드 추가:
```python
def _get_cookies_file_path(self) -> Optional[str]:
    if not self.cookies:
        return None
    import os
    from app.core.config import settings
    cookies_dir = settings.DATA_DIR
    os.makedirs(cookies_dir, exist_ok=True)
    cookie_path = os.path.join(cookies_dir, "tiktok_cookies.txt")
    with open(cookie_path, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for name, value in self.cookies.items():
            f.write(f".tiktok.com\tTRUE\t/\tTRUE\t0\t{name}\t{value}\n")
    return cookie_path
```

2. `get_streamlink_args()` 수정 (빈 리스트 → 쿠키 포함):
```python
def get_streamlink_args(self) -> list:
    args = ["--no-playlist", "--socket-timeout", "15", "--retries", "10"]
    cookie_file = self._get_cookies_file_path()
    if cookie_file:
        args.extend(["--cookies", cookie_file])
    return args
```

3. `_extract_with_ytdlp()`에도 쿠키 전달:
```python
async def _extract_with_ytdlp(self) -> dict:
    def extract():
        ydl_opts = {
            'quiet': True, 'simulate': True, 'no_warnings': True, 'extract_flat': False
        }
        cookie_file = self._get_cookies_file_path()
        if cookie_file:
            ydl_opts['cookiefile'] = cookie_file
        # ... 기존 로직 ...
```

---

### Step B4: Kick — Cloudflare 우회 강화

**파일**: `app/extractors/kick.py`

1. `_extract_with_ytdlp()`에 쿠키 전달 추가:
```python
async def _extract_with_ytdlp(self) -> dict:
    def extract():
        ydl_opts = {
            'quiet': True, 'simulate': True, 'no_warnings': True,
        }
        cookie_str = self.get_cookie_string()
        if cookie_str:
            ydl_opts['http_headers'] = {
                'Cookie': cookie_str,
                'User-Agent': self.headers.get("User-Agent", ""),
            }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                return ydl.extract_info(f"https://kick.com/{self.channel_id}", download=False)
            except Exception as e:
                logger.debug(f"[Kick] yt-dlp 추출 실패 ({self.channel_id}): {e}")
                return None
    return await asyncio.to_thread(extract)
```

2. (선택) Kick API v2 직접 호출 fallback:
```python
async def _check_via_api(self) -> dict:
    url = f"https://kick.com/api/v2/channels/{self.channel_id}"
    return await self._fetch_json(url)
```

---

## Phase C: VOD 다운로드 확장

### Step C1: vod_downloader.py 범용화

**파일**: `app/services/vod_downloader.py`

URL 패턴으로 플랫폼 자동 감지하는 함수 추가:
```python
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
```

기존 `download_vod_task()`를 플랫폼별 cmd 분기로 수정.

### Step C2-C4: SOOP/TikTok/Kick VOD

각 플랫폼 VOD URL을 yt-dlp로 다운로드하도록 `_build_vod_command()` 함수에 분기 추가.
기본 패턴:
```python
cmd = [settings.YTDLP_PATH, "--no-playlist", "-o", output_template, url]
```

---

## 📌 작업 완료 후 체크리스트

- [ ] Phase A (4건) 완료 + work_log.md 기록
- [ ] Phase B (4건) 완료 + work_log.md 기록
- [ ] Phase C (4건) 완료 + work_log.md 기록
- [ ] 서버 정상 기동 확인 (`uvicorn app.main:app`)
- [ ] README.md 지원 현황표 업데이트
- [ ] Claude Opus 리뷰 요청 준비

---

> **작업 완료 후 사용자에게 "Claude Opus 리뷰 요청"을 안내하세요.**
