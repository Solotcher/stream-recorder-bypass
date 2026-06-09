# Stream Recorder Bypass (다중 플랫폼 자동 우회 녹화기)

치지직(Chzzk), 아프리카TV(SOOP), 트위치(Twitch), 유튜브(YouTube), 틱톡(TikTok), 킥(Kick), 인스타그램(Instagram) 라이브 방송을 모니터링하고 자동으로 녹화하며, 유튜브/치지직 VOD 비동기 다운로드 및 강력한 봇 디텍션 우회 기능을 지원하는 **엔터프라이즈급 아키텍처 웹 애플리케이션**입니다.

## 핵심 특징

- **멀티 플랫폼 우회(Bypass)**: Cloudflare Turnstile(Kick), 모바일 웹 HTML 파싱 선검지(TikTok/YouTube Live), API 차단 대비 정적 HTML 폴백(SOOP) 등 고도화된 우회 엔진 내장.
- **백그라운드 VOD 고속 다운로드**: 유튜브 및 치지직 VOD URL만 입력하면 분할 병렬 다운로드(DASH/aria2c) 및 구간 크롭(-ss/-t) 다운로드 지원.
- **엔터프라이즈급 안정성**: 
  - 동시성 무결성을 확보한 **SQLite (+ SQLAlchemy 객체 매핑)** 기반 채널 저장소.
  - 무거운 FFmpeg 인코딩 및 후처리 작업을 완벽히 분리한 **Celery + Redis 기반 비동기 분산 워커 큐**.
- **의존성 자동 관리**: 실행 시 환경(Windows/Linux)에 맞춰 FFmpeg, Streamlink, yt-dlp를 자동 감지하여 설치 및 자가 백업 업데이트 수행.
- **다중 비동기 로깅 컨텍스트**: Trace ID를 활용해 다중 채널이 비동기로 병렬 구동 및 후처리되는 전 과정의 로그가 꼬임 없이 완벽히 추적됩니다.
- **클라우드 자동 업로드**: rclone 연동으로 녹화 완료 즉시 원격 구글 드라이브 등 클라우드에 자동 백업 및 디스크 용량 자동 관리.

---

## 설치 및 실행 방법 (권장 환경: Docker 기반 Python 3.14 OCI 배포)

이 프로그램은 Docker를 통한 `docker-compose` 배포를 가장 강력히 권장합니다.

### 0. Docker (공식 배포 규격)

```bash
# 저장소 클론 (Bypass 에디션)
git clone https://github.com/Solotcher/stream-recorder-bypass.git
cd stream-recorder-bypass

# 백그라운드 컨테이너 빌드 및 론칭
docker compose up -d --build
```
*위 명령어 한 줄로 **Python 3.14 (Free-threaded/No-GIL)** 기반의 메인 서버 컨테이너, **Redis** 메시지 브로커 컨테이너, 그리고 인코딩 전담 **Celery 워커** 컨테이너가 일괄 구축되며 하드웨어의 병렬 성능이 100% 해제됩니다.* 녹화된 결과물은 호스트 PC of `./output` 에 영구 저장됩니다.

---

## 환경 설정 (.env)

최초 실행 시 `.env` 파일이 생성됩니다. 다음 항목을 프로젝트 상황에 맞게 수정하세요:

- `OUTPUT_DIR`: 녹화 파일 저장 경로 (Docker 구동 시 수정 불필요, `docker-compose.yml` 바인드 마운트 활용 권장)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`: 상태 알림 전송용 텔레그램 봇
- `FILENAME_PATTERN`: 파일명 생성 규칙 (예: `{date}_{time}_{streamer}_{title}_{quality}`)
- `RCLONE_REMOTE`: 클라우드 연동 업로드 리모트
- `USER_AGENT`: 모바일 & PC 크롤링 우회용 User-Agent

---

## 사용 방법

1. 대시보드 진입: 브라우저에서 `http://localhost:8000` (클라우드 구동 시 서버IP:8000) 접속.
2. **채널 관리** 탭에서 플랫폼 선택 후 스트리머 ID 또는 URL을 입력하여 추가하세요.
   - 치지직: `chzzk.naver.com/채널ID`
   - 트위치: `twitch.tv/아이디`
   - 유튜브: `youtube.com/@핸들` 또는 `youtube.com/channel/UC채널ID`
   - 숲(SOOP): `ch.soop.st/아이디` 또는 `play.soop.st/방번호`
   - 킥: `kick.com/채널ID`
   - 틱톡/인스타그램: 각 플랫폼 계정 ID (`@` 생략 가능)
3. **쿠키 관리** 탭에서 플랫폼별 멤버십 방송 녹화 및 성인 인증을 위한 브라우저 우회 전용 쿠키를 간편하게 뭉치 복사로 등록할 수 있습니다.

---

## 기술 스택 (Tech Stack)

- **Backend**: FastAPI (Python 3.14 튜닝), Pydantic
- **Database**: SQLite & SQLAlchemy ORM
- **Background Queue**: Celery, Redis (비동기 인코딩 및 VOD 병합 파이프라인 전담)
- **Frontend**: Vanilla JS (ES Modules), CSS (Glassmorphism & Interactive UI)
- **추출 및 우회 엔진**: curl_cffi (Kick Turnstile 우회), Streamlink (Chzzk, Twitch, SOOP, Instagram), yt-dlp (YouTube), Mobile HTML Web Scraping (TikTok)
- **후처리**: FFmpeg (Remuxing / Concat)

---

## 🤖 AI 개발 안내

이 프로젝트의 모든 아키텍처 인프라 코드와 프론트엔드/백엔드 비즈니스 로직은 **100% AI에 의해 작성**되었습니다.

**사용된 AI 모델:**
- **Claude Opus 4.6** (Anthropic) — 핵심 아키텍처 기반 설계, 백엔드/프론트엔드 전체 초기 구현, 레거시 버그 수정
- **Gemini 3.1 Pro(High)** (Google DeepMind) — 전반적인 시스템 고도화, 신규 플랫폼(TikTok, Instagram) 확장, OCI 클라우드 및 Docker(3.14 No-GIL) 체제 이식, SQLite 및 Celery+Redis를 관통하는 차세대 아키텍처 전면 개편(Phase 1~3 완전 수행)
- **Antigravity (Gemini 3.5 Flash (Medium))** — 4대 플랫폼(SOOP, 유튜브 라이브, 틱톡, 킥) 초경량 하이브리드 우회(Bypass) 아키텍처 및 Trace ID 로깅 코어 탑재. 프로젝트 이관 아카이빙 분리 및 신규 개발 작업 환경 구축 완료.

---

## 기여 및 문의

배포 및 실행 중 발생하는 장애, 추가 플랫폼 연동 기능이 필요한 경우 이슈 영역을 통해 피드백을 남겨주시면 감사히 검토하겠습니다.
