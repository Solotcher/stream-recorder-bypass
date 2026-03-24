# Python 3.14 Slim 버전을 베이스로 사용 (No-GIL 환경 테스트 대비)
FROM python:3.14-slim

# OS의 시간대(Timezone) 설정 및 백그라운드 필수 의존성 추가
ENV TZ=Asia/Seoul
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    git \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 작업 디렉토리 생성 및 지정
WORKDIR /app

# 파이썬 의존성 패키지 복사 및 캐시 지시
COPY requirements.txt .

# PIP 업그레이드 및 필수 라이브러리 설치
# (No-GIL 가상 환경이 아닌 Docker 전역 환경 활용)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 프로젝트 전체 복사
COPY . .

# FastAPI의 Uvicorn 웹 서버 기본 노출 포트
EXPOSE 8000

# 프로젝트 엔트리 포인트 (안정성 보장을 위해 표준 런타임 사용)
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
