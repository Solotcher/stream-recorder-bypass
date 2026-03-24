"""
Command Pattern 기반 녹화 커맨드 빌더 모듈.
trigger_recording의 God Function을 분해하여 SRP를 준수합니다.
"""
from app.commands.base import CommandBuilder
from app.commands.streamlink_builder import StreamlinkCommandBuilder
from app.commands.ytdlp_builder import YtdlpCommandBuilder
from app.commands.filename_generator import (
    safe_text, resolve_display_quality, generate_filename, build_output_path
)

__all__ = [
    "CommandBuilder",
    "StreamlinkCommandBuilder",
    "YtdlpCommandBuilder",
    "safe_text",
    "resolve_display_quality",
    "generate_filename",
    "build_output_path",
]
