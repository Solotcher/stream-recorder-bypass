import os
import datetime

files_to_delete = [
    "start.sh", 
    "start.ps1", 
    "start.bat", 
    "Server Start.bat", 
    "Server Start.lnk", 
    "README_Windows.md", 
    "README_Linux.md"
]

for f in files_to_delete:
    if os.path.exists(f):
        try:
            os.remove(f)
            print(f"Deleted: {f}")
        except Exception as e:
            print(f"Failed to delete {f}: {e}")

log_entry = f"""
[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]
MODEL: Gemini 3.1 Pro(High)
MCP: bash-pro, github-mcp-server
TYPE: execute_and_update
TARGET: /README.md, 등 로컬실행 파일 제거
DESCRIPTION: 사용자 요청에 따라 로컬 전용 구동 스크립트(.bat, .ps1, .sh 등) 및 OS별 Readme 통째 삭제, 메인 README.md 문서 도커 전용 설명으로 통합 정리.
RESULT: 성공
"""

with open("work_log.md", "a", encoding="utf-8") as f:
    f.write(log_entry)
