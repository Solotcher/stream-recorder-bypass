import datetime

log_entry = f"""
[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]
MODEL: Gemini 3.1 Pro(High)
MCP: bash-pro, github-mcp-server
TYPE: code_modify
TARGET: /frontend/api.js, /app/services/scheduler.py
DESCRIPTION: Phase 5 - VOD URL 수동녹화 입력란 패스스루 라우팅 추가 (유튜브/SOOP), 틱톡 레코더 파이프라인 FFmpeg 403 회피를 위해 yt-dlp 네이티브 방식으로 전면 교체.
RESULT: 성공
"""

with open("work_log.md", "a", encoding="utf-8") as f:
    f.write(log_entry)
