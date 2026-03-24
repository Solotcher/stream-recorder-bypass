import datetime

log_entry = f"""
[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]
MODEL: Gemini 3.1 Pro(High)
MCP: bash-pro, github-mcp-server
TYPE: code_modify
TARGET: /app/extractors/tiktok.py
DESCRIPTION: Phase 5 추가 수정 - 틱톡 추출기에서 yt-dlp 메타데이터 파싱 시 순수 숫자(uploader_id)가 아닌 닉네임(uploader)이 우선 파싱되도록 변경. 프론트엔드 캐시 적용 방안 가이드 준비.
RESULT: 성공
"""

with open("work_log.md", "a", encoding="utf-8") as f:
    f.write(log_entry)
