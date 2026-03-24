"""
Streamlink 기반 녹화 커맨드 빌더.
대상 플랫폼: 치지직(Chzzk), 트위치(Twitch), SOOP, 인스타그램(Instagram)

기존 scheduler.py L141-145의 Streamlink 커맨드 조립 로직을 이관합니다.
"""
from typing import List, Optional

from app.commands.base import CommandBuilder
from app.core.config import settings


class StreamlinkCommandBuilder(CommandBuilder):
    """Streamlink CLI 커맨드를 조립하는 빌더"""

    def build_command(
        self,
        stream_url: str,
        output_path: str,
        resolution: str = "best",
        extra_args: Optional[List[str]] = None
    ) -> List[str]:
        cmd = [settings.STREAMLINK_PATH]

        if extra_args:
            cmd.extend(extra_args)

        cmd.extend([stream_url, resolution, "-o", output_path])
        return cmd

    def get_output_extension(self) -> str:
        return ".ts"

    def needs_remuxing(self) -> bool:
        return True
