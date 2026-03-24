# Stream Recorder 프로젝트 - AI 에이전트 인수인계서 (Handover Document)

이 문서는 사용자의 일일 사용 할당량 초과 또는 세션 전환 시점 단위로 작성된 인수인계 파일입니다. 다음 에이전트는 **반드시 본 문서와 `work_log.md`를 먼저 숙지하고 작업을 이어나가야 합니다.**

---

## 1. 최근 작업 요약 (Session Summary)
- **발생 일시**: 2026-03-24 13:20 KST
- **사용 모델 (Last Used Model)**: Gemini 3.1 Pro (High)
- **사용 필수 MCP**: 
  - `default_api`: 파일 파싱 및 수정, 터미널(도커) 직접 제어
  - `TestSprite` (권장): 코드 테스트, 변경 전후 렌더링 무결성 확인용
  - `Sequential Thinking` (복잡도 분석 시): HTML 및 JavaScript의 DOM 조작 오버라이드 로직의 복잡한 상관관계를 파악할 때 사용

### ✅ 달성된 결과물 (Phase 4, 5)
- 수동 즉시 녹화 입력창과 현재 녹화 현황 표를 상하 하나로 이어붙인 **'대시보드(Dashboard)'** UI 신규 구축.
- Docker Inode 변질 에러 해결을 위해 `.env` 파일을 로컬 마운트인 `data/.env`로 완전히 이관함.
- 틱톡 0KB 녹화 에러 해결 위해 `scheduler.py`에 yt-dlp `--hls-prefer-native` 스위치 주입 완료.

---

## 2. 해결되지 않은 치명적 이슈 (Current Blocker)

### 🚨 "대시보드 중간 제목줄 렌더링 누락 버그"
- **현상**: 웹브라우저(`http://localhost:8000`)에 접속했을 때, **"🔴 실시간 백그라운드 녹화 현황"** 이라는 `<h3>` 노드 요소가 **화면에 출력되지 않음.**
- **기존 확인된 팩트 (할루시네이션 방지 필수!)**:
  1. 서버는 **정확히 최신 HTML**을 내려주고 있음. (내부 Powershell과 `read_url_content` 요청 패킷으로 뜯어봤을 때 해당 `<h3>` 태그가 100% 정상 포함되어 있음 확인 완료)
  2. 사용자의 운영 환경인 **D드라이브(`D:\Downloader\stream-recorder`)**의 파일에도 코드가 정상 동기화되어 있으며, 도커 역시 최신 상태로 재빌드 완료됨.
  3. 즉, 원인은 **서버나 도커 측의 파일 미반영(X)**이 절대 아니라, **해당 웹페이지를 그리는 클라이언트(브라우저) 내부 논리 오류(O)** 임.

---

## 3. 다음 작업자(Next Agent) 행동 강령 및 권장 플랜

다음 에이전트가 접속하면 아래 순서대로 디버깅 및 개발을 착수해야 합니다.

### 🎯 Step 1: DOM 파싱/충돌 정밀 분석
- 브라우저에 다운로드된 HTML 태그가 `style.css` 또는 `script.js`에 의해 가려지거나 파괴되고 있는지 분석해야 함.
- **권장 방식**: `view_file` MCP를 사용하여 `frontend/style.css`에서 `view-dashboard` 영역 하위 자식 노드의 `margin` 충돌 겹침 요소가 있는지 탐색.

### 🎯 Step 2: 자바스크립트 오버라이드 탐지
- `frontend/api.js` 내부의 `fetchActiveJobs()` 렌더링 함수 등이 간접적인 부모 노드에 `innerHTML` 등을 덮어씌워서 기껏 추가한 타이틀(`<div style="...">`)을 브라우저 파서가 지워버리는 것은 아닌지 분석. (현재 육안상으로는 `activeJobsTbody.innerHTML = html` 구문만 있는 것으로 확인했으나 더 상위 scope 탐색 권장)

### 🎯 Step 3 (우회 해결책): DOM 위치 변경 적용
- 단순히 CSS float, flex, margin 겹침 버그라면 코드 구조를 고치는 데 시간이 오래 걸릴 수 있으므로 **가장 안전한 방법**으로 픽스를 제시할 것.
- `index.html` 내의 `"🔴 실시간 백그라운드 녹화 현황"` 태그를 `div.glass-card` 사이의 애매한 여백이 아닌, **`table` 태그가 있는 `glass-card` 요소의 바로 첫 줄 하위 요소**로 이사시켜 버릴 것.
- 변경 후 `TestSprite` 혹은 `run_command`로 D드라이브 운영 폴더의 도커를 재가동(`docker compose restart stream-recorder-app`) 하여 사용자에게 테스트를 유도.

### 🎯 Step 4: [필수 규칙] 작업 로그 작성
- **사용자 전역 필수 규칙**에 따라 작업 시 반드시 `D:\Downloader\stream-recorder\work_log.md`를 갱신해야 합니다. (형식은 기존 파일의 포맷 참조)
