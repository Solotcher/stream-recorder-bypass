# 🔧 인수인계: Remuxer 텔레그램 알림 `No module named 'app'` 에러 수정

> **작성일**: 2026-04-09
> **작성자**: Claude Opus 4.6 (Thinking)
> **대상 모델**: 저렴한 모델 (Flash 등)
> **난이도**: ★★☆☆☆ (단순 코드 수정)
> **예상 소요**: 15분

---

## 📌 문제 요약

remuxer 사이드카 컨테이너에서 `.ts` → `.mp4` 리먹싱 완료 후 텔레그램 알림 전송 시 에러 발생:

```
[ERROR] [remuxer] 완료 알림 전송 실패: No module named 'app'
```

## 🔍 원인

`scripts/remuxer.py`가 텔레그램 알림을 보내려고 아래 코드를 실행:

```python
from app.utils.telegram_bot import send_telegram_message   # 108행
from app.utils.telegram_bot import send_error_alert         # 133행, 141행
```

remuxer는 `python -u scripts/remuxer.py`로 실행되는데, 이 때 Python의 `sys.path`에 `/app`이 포함되지 않아서 `app` 패키지를 찾지 못함. 또한 remuxer 컨테이너에는 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 환경변수도 전달되지 않고 있음.

## ✅ 해결 방법

`app` 패키지에 의존하지 않도록, remuxer 자체에 텔레그램 전송 함수를 내장한다. 표준 라이브러리 `urllib`만 사용하여 외부 의존성 없이 동작하게 만든다.

---

## 📝 수정할 파일 2개

### 1. `scripts/remuxer.py`

#### 변경 1: import 추가 (파일 상단)

**위치**: 1~11행 (기존 import 블록)

기존 import 블록 끝(`from watchdog.events import FileSystemEventHandler` 다음)에 추가:

```python
import json
import urllib.request
import urllib.error
```

#### 변경 2: RemuxConfig 클래스에 텔레그램 설정 추가

**위치**: 14~19행 (`class RemuxConfig:`)

기존 코드:
```python
class RemuxConfig:
    WATCH_DIR = os.environ.get("REMUX_WATCH_DIR", "/app/output")
    CONCURRENCY = int(os.environ.get("REMUX_CONCURRENCY", "2"))
    RETRY_DELAY = int(os.environ.get("REMUX_RETRY_DELAY", "300"))
    STABLE_CHECK = int(os.environ.get("REMUX_STABLE_CHECK", "30"))
    MIN_SIZE = int(os.environ.get("REMUX_MIN_SIZE", "1024"))
```

변경 후:
```python
class RemuxConfig:
    WATCH_DIR = os.environ.get("REMUX_WATCH_DIR", "/app/output")
    CONCURRENCY = int(os.environ.get("REMUX_CONCURRENCY", "2"))
    RETRY_DELAY = int(os.environ.get("REMUX_RETRY_DELAY", "300"))
    STABLE_CHECK = int(os.environ.get("REMUX_STABLE_CHECK", "30"))
    MIN_SIZE = int(os.environ.get("REMUX_MIN_SIZE", "1024"))
    # 텔레그램 알림 설정
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
```

#### 변경 3: 독립 텔레그램 전송 함수 추가

**위치**: `RemuxConfig` 클래스 바로 아래, logger 설정 블록 바로 아래 (28행 다음)에 삽입

아래 함수 2개를 추가:

```python
def send_telegram_notification(message: str) -> bool:
    """remuxer 전용 텔레그램 알림 전송 (표준 라이브러리만 사용)"""
    token = RemuxConfig.TELEGRAM_BOT_TOKEN
    chat_id = RemuxConfig.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return True
            logger.warning(f"텔레그램 응답 코드: {resp.status}")
    except Exception as e:
        logger.warning(f"텔레그램 알림 전송 실패 (무시): {e}")
    return False


def send_telegram_error(channel_name: str, context: str, error_msg: str):
    """remuxer 전용 에러 알림 전송"""
    safe_err = str(error_msg).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    msg = (
        f"🚨 <b>시스템 에러 알림</b> 🚨\n\n"
        f"채널명: <b>{channel_name}</b>\n"
        f"발생위치: {context}\n"
        f"오류내용:\n<code>{safe_err}</code>"
    )
    send_telegram_notification(msg)
```

#### 변경 4: remux() 메서드 내 텔레그램 호출 3곳 교체

**위치 A**: 104~116행 (리먹싱 성공 시 알림)

기존:
```python
                    # 텔레그램 완료 알림 전송
                    try:
                        import asyncio
                        from app.utils.telegram_bot import send_telegram_message
                        filename = os.path.basename(mp4_path)
                        asyncio.run(send_telegram_message(
                            f"🎬 <b>리먹싱(변환) 완료</b>\n\n"
                            f"파일: <code>{filename}</code>\n"
                            f"크기: <b>{mp4_size // (1024*1024)} MB</b>"
                        ))
                    except Exception as e:
                        logger.error(f"완료 알림 전송 실패: {e}")
```

변경 후:
```python
                    # 텔레그램 완료 알림 전송
                    filename = os.path.basename(mp4_path)
                    send_telegram_notification(
                        f"🎬 <b>리먹싱(변환) 완료</b>\n\n"
                        f"파일: <code>{filename}</code>\n"
                        f"크기: <b>{mp4_size // (1024*1024)} MB</b>"
                    )
```

**위치 B**: 131~136행 (리먹싱 실패 시 알림)

기존:
```python
                try:
                    import asyncio
                    from app.utils.telegram_bot import send_error_alert
                    asyncio.run(send_error_alert(os.path.basename(ts_path), "remuxer 컨테이너", err_text))
                except Exception:
                    pass
```

변경 후:
```python
                send_telegram_error(os.path.basename(ts_path), "remuxer 컨테이너", err_text)
```

**위치 C**: 139~144행 (타임아웃 시 알림)

기존:
```python
            try:
                import asyncio
                from app.utils.telegram_bot import send_error_alert
                asyncio.run(send_error_alert(os.path.basename(ts_path), "remuxer 컨테이너", f"타임아웃 {timeout}초 초과"))
            except Exception:
                pass
```

변경 후:
```python
            send_telegram_error(os.path.basename(ts_path), "remuxer 컨테이너", f"타임아웃 {timeout}초 초과")
```

---

### 2. `docker-compose.yml`

**위치**: 53~69행 (remuxer 서비스 블록)

remuxer 서비스의 `environment` 섹션에 텔레그램 환경변수 2개 추가:

기존:
```yaml
  remuxer:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: stream-recorder-remuxer
    restart: unless-stopped
    command: ["python", "-u", "scripts/remuxer.py"]
    volumes:
      - ./output:/app/output
    environment:
      - TZ=Asia/Seoul
      - REMUX_WATCH_DIR=/app/output
      - REMUX_CONCURRENCY=2
      - REMUX_RETRY_DELAY=300
      - REMUX_STABLE_CHECK=30
```

변경 후:
```yaml
  remuxer:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: stream-recorder-remuxer
    restart: unless-stopped
    command: ["python", "-u", "scripts/remuxer.py"]
    volumes:
      - ./output:/app/output
    environment:
      - TZ=Asia/Seoul
      - REMUX_WATCH_DIR=/app/output
      - REMUX_CONCURRENCY=2
      - REMUX_RETRY_DELAY=300
      - REMUX_STABLE_CHECK=30
      # 리먹싱 완료/실패 시 텔레그램 알림 전송용
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID:-}
```

> **참고**: `${TELEGRAM_BOT_TOKEN:-}`는 호스트의 `.env` 파일이나 환경변수에서 자동으로 값을 가져옵니다. 값이 없으면 빈 문자열이 됩니다.

---

## 🧪 검증 방법

1. 수정 완료 후 Docker 재빌드:
   ```bash
   docker-compose up -d --build remuxer
   ```

2. remuxer 로그 확인:
   ```bash
   docker-compose logs -f remuxer
   ```

3. 테스트용 `.ts` 파일을 `output/` 하위 폴더에 복사하여 리먹싱이 트리거되는지 확인

4. 텔레그램 알림이 정상 수신되는지 확인

---

## ⚠️ 주의사항

- `asyncio.run()`을 제거하고 **동기 방식** `urllib`로 교체하는 것이 핵심입니다
- `app` 패키지에서 아무것도 import하면 안 됩니다 (remuxer는 독립 사이드카)
- `send_telegram_notification()` 함수는 실패해도 예외를 던지지 않고 `False`만 반환합니다 (리먹싱 작업에 영향 없음)

---

## 📋 작업 완료 후 work_log.md에 추가할 내용

```
[2026-04-09 HH:MM:SS]
MODEL: (사용한 모델명)
MCP: filesystem
TYPE: bug_fix
TARGET: scripts/remuxer.py, docker-compose.yml
DESCRIPTION: remuxer 사이드카 컨테이너의 텔레그램 알림 전송 실패(No module named 'app') 버그 수정. app 패키지 의존성을 제거하고 표준 라이브러리 urllib 기반의 독립적 텔레그램 전송 함수로 교체. docker-compose.yml에 텔레그램 환경변수 전달 추가.
RESULT: 성공
```
