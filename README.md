# Stream Recorder (다중 플랫폼 자동 녹화기)

치지직(Chzzk), 아프리카TV(SOOP), 트위치(Twitch), 유튜브(YouTube), 틱톡(TikTok) 라이브, 인스타그램(Instagram) 라이브 방송을 모니터링하고 자동으로 녹화하며, 유튜브 VOD 비동기 다운로드 기능을 지원하는 **엔터프라이즈급 아키텍처 웹 애플리케이션**입니다.

## 📺 현재 지원 플랫폼 현황

| 상태 | 플랫폼 | 지원 기능 |
| :--- | :--- | :--- |
| **✅ 정상 작동** | **치지직(Chzzk)** | 라이브 자동 녹화 |
| | **유튜브(YouTube)** | 동영상(VOD) 비동기 다운로드 |
| **❌ 지원 불가/오류** | **유튜브(YouTube)** | 라이브 녹화 (미지원) |
| | **숲(SOOP)** | 라이브 및 VOD 녹화 (로직 오류) |
| | **틱톡(TikTok)** | 라이브 및 VOD 녹화 (접근 제한) |
| | **킥(Kick)** | 라이브 및 VOD 녹화 (미지원) |

> [!WARNING]
> **플랫폼 서비스 안내**: 현재 SOOP, 틱톡 등 일부 플랫폼의 녹화 로직에 구조적 문제가 있어 원활한 녹화가 이루어지지 않을 수 있습니다. 특히 유튜브 라이브와 킥은 현재 정식 지원 범위에서 제외되어 있으니 사용 시 참고 부탁드립니다.

## 핵심 특징

- **멀티 플랫폼 완벽 대응**: Chzzk, SOOP, Twitch, YouTube 라이브는 물론 신규 연동된 **TikTok**, **Instagram Live** 모니터링 및 녹화를 기본 지원합니다.
- **백그라운드 VOD 다운로드**: 유튜브 VOD URL만 던지면 워커가 백그라운드에서 다운로드 후 서버에 저장해 줍니다.
- **엔터프라이즈급 안정성**: 
  - 과거 JSON 파일 I/O로 인한 병목 현상을 타파하고 **SQLite (+ SQLAlchemy 객체 매핑)** 기반 시스템으로 마이그레이션하여 동시성 무결성을 보장합니다.
  - 무거운 FFmpeg 인코딩 및 다운로드 작업을 메인 서버에서 떼어내 **Celery + Redis 기반 비동기 분산 워커 큐**로 오프로딩시켰습니다.
- **의존성 자동 관리**: FFmpeg, Streamlink, yt-dlp가 없어도 실행 시 자동으로 환경에 맞춰 최신 버전으로 다운로드/업데이트됩니다.
- **자동 리먹싱 & 후처리 보호**: 녹화 완료 후 MP4 형식으로 자동 변환. 실패 시 원본 파일(.ts)이 안전하게 보존되며 에러 로그가 남습니다.
- **클라우드 자동 업로드**: rclone 연동으로 녹화 완료 후 구글 드라이브 등 클라우드에 100% 자동 백업 및 용량 확보.

---

## 설치 및 실행 방법 (권장 환경: Docker 기반 Python 3.14 OCI 배포)

이 프로그램은 Docker를 통한 `docker-compose` 배포를 가장 강력히 권장합니다.

### 0. Docker (공식 배포 규격)

```bash
# 저장소 클론
git clone https://github.com/Solotcher/stream-recorder.git
cd stream-recorder

# 백그라운드 컨테이너 빌드 및 론칭
docker compose up -d --build
```
*위 명령어 한 줄로 **Python 3.14 (Free-threaded/No-GIL)** 기반의 메인 서버 컨테이너, **Redis** 메시지 브로커 컨테이너, 그리고 인코딩 전담 **Celery 워커** 컨테이너가 일괄 구축되며 하드웨어의 병렬 성능이 100% 해제됩니다.* 녹화된 결과물은 호스트 PC의 `./output` 에 영구 저장됩니다.

---

## 환경 설정 (.env)

최초 실행 시 `.env` 파일이 생성됩니다. 다음 항목을 프로젝트 상황에 맞게 수정하세요:

- `OUTPUT_DIR`: 녹화 파일 저장 경로 (Docker 구동 시 수정 불필요, `docker-compose.yml` 바인드 마운트 활용 권장)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`: 상태 알림 전송용 텔레그램 봇
- `FILENAME_PATTERN`: 파일명 생성 규칙 (예: `{date}_{streamer}_{title}_{quality}`)
- `RCLONE_REMOTE`: 클라우드 연동 업로드 리모트
- `USER_AGENT`: 모바일 & PC 크롤링 우회용 User-Agent

---

## 사용 방법

1. 대시보드 진입: 브라우저에서 `http://localhost:8000` (클라우드 구동 시 서버IP:8000) 접속.
2. **채널 관리** 탭에서 플랫폼 선택 후 스트리머 ID 또는 URL을 입력하여 추가하세요.
   - 치지직: `chzzk.naver.com/채널ID`
   - 트위치: `twitch.tv/아이디`
   - 유튜브: `youtube.com/@핸들` 또는 `youtube.com/channel/UC채널ID`
   - 틱톡/인스타그램: 각 플랫폼 계정 ID (`@` 생략 가능)
3. **쿠키 관리** 탭에서 인스타그램, 틱톡 등의 멤버십 방송 녹화 및 밴 우회를 위한 브라우저 우회 전용 쿠키를 입양할 수 있습니다.

---

## 기술 스택 (Tech Stack)

- **Backend**: FastAPI (Python 3.14 튜닝), Pydantic
- **Database**: SQLite & SQLAlchemy ORM
- **Background Queue**: Celery, Redis (비동기 인코딩 및 VOD 병합 파이프라인 전담)
- **Frontend**: Vanilla JS (ES Modules), CSS (Glassmorphism & Interactive UI)
- **추출 및 녹화 엔진**: Streamlink (Chzzk, Twitch, SOOP, Instagram), yt-dlp (YouTube), FFmpeg Native (TikTok)
- **후처리**: FFmpeg (Remuxing / Concat)

---

## 🤖 AI 개발 안내

이 프로젝트의 모든 아키텍처 인프라 코드와 프론트엔드/백엔드 비즈니스 로직은 **100% AI에 의해 작성**되었습니다.

**사용된 AI 모델:**
- **Claude Opus 4.6** (Anthropic) — 핵심 아키텍처 기반 설계, 백엔드/프론트엔드 전체 초기 구현, 레거시 버그 수정
- **Gemini 3.1 Pro(High)** (Google DeepMind) — 전반적인 시스템 고도화, 신규 플랫폼(TikTok, Instagram) 확장, OCI 클라우드 및 Docker(3.14 No-GIL) 체제 이식, SQLite 및 Celery+Redis를 관통하는 차세대 아키텍처 전면 개편(Phase 1~3 완전 수행)

---

## 기여 및 문의

배포 및 실행 중 발생하는 장애, 추가 플랫폼 연동 기능이 필요한 경우 이슈 영역을 통해 피드백을 남겨주시면 감사히 검토하겠습니다.
