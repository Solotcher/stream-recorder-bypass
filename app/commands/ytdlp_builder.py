"""
yt-dlp 기반 녹화 커맨드 빌더.
대상 플랫폼: 유튜브(YouTube), 틱톡(TikTok)

기존 scheduler.py L128-140의 유튜브/틱톡 커맨드 조립 로직을 이관합니다.
"""
from typing import List, Optional

from app.commands.base import CommandBuilder
from app.core.config import settings


class YtdlpCommandBuilder(CommandBuilder):
    """yt-dlp CLI 커맨드를 조립하는 빌더"""

    def __init__(self, platform: str, channel_id: str = ""):
        self.platform = platform
        self.channel_id = channel_id

    def build_command(
        self,
        stream_url: str,
        output_path: str,
        resolution: str = "best",
        extra_args: Optional[List[str]] = None
    ) -> List[str]:
        if self.platform == "tiktok":
            return self._build_tiktok_command(output_path)

        return self._build_youtube_command(stream_url, output_path, extra_args)

    def _build_youtube_command(
        self,
        stream_url: str,
        output_path: str,
        extra_args: Optional[List[str]] = None
    ) -> List[str]:
        """유튜브: yt-dlp + extractor.get_streamlink_args() 결과"""
        cmd = [settings.YTDLP_PATH]

        if extra_args:
            cmd.extend(extra_args)

        cmd.extend(["-o", output_path, stream_url])
        return cmd

    def _build_tiktok_command(self, output_path: str) -> List[str]:
        """틱톡: @핸들/live URL + --no-playlist"""
        tiktok_url = f"https://www.tiktok.com/@{self.channel_id}/live"
        return [
            settings.YTDLP_PATH,
            tiktok_url,
            "--no-playlist",
            "-o", output_path
        ]

    def get_output_extension(self) -> str:
        return ".mp4"

    def needs_remuxing(self) -> bool:
        return False
