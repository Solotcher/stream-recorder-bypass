import asyncio
from typing import Dict, Any, Optional
from app.extractors.base_extractor import BaseExtractor
from app.core.logger import logger
import yt_dlp

class KickExtractor(BaseExtractor):
    """
    Kick Live 스트림 추출기.
    
    Kick은 강력한 Cloudflare 방어를 가지므로, yt-dlp의 내장 우회 기능을 사용하여 메타데이터를 파싱합니다.
    """

    def __init__(self, channel_id: str, cookies: Optional[Dict[str, str]] = None):
        super().__init__(channel_id, cookies)

    async def _extract_with_ytdlp(self) -> dict:
        def extract():
            ydl_opts = {
                'quiet': True,
                'simulate': True,
                'no_warnings': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    return ydl.extract_info(f"https://kick.com/{self.channel_id}", download=False)
                except Exception as e:
                    logger.debug(f"[Kick] yt-dlp 추출 실패 ({self.channel_id}): {e}")
                    return None
        return await asyncio.to_thread(extract)

    async def is_live(self) -> bool:
        info = await self._extract_with_ytdlp()
        if info and info.get("is_live"):
            return True
        return False

    async def get_metadata(self) -> Dict[str, Any]:
        info = await self._extract_with_ytdlp()
        if not info or not info.get("is_live"):
            return {"status": "CLOSE", "channel_name": self.channel_id}
            
        return {
            "status": "OPEN",
            "title": info.get("title", f"{self.channel_id} Kick Live"),
            "channel_name": info.get("uploader_id") or info.get("uploader") or self.channel_id,
            "nickname": info.get("uploader", self.channel_id),
            "thumbnail_url": info.get("thumbnail", ""),
            "viewer_count": info.get("view_count", 0),
        }

    async def get_channel_info(self) -> Dict[str, Any]:
        return {"channel_name": self.channel_id}

    def get_streamlink_args(self) -> list:
        """Kick은 Streamlink 공식 플러그인이 내장되어 있으므로 기본 아규먼트를 이용합니다."""
        args = [
            f"https://kick.com/{self.channel_id}",
            "best",
            "--hls-live-restart"
        ]
        return args
