import asyncio
from typing import Dict, Any, Optional
from app.extractors.base_extractor import BaseExtractor
from app.core.logger import logger
import yt_dlp

class TikTokExtractor(BaseExtractor):
    """
    TikTok Live 스트림 추출기.
    
    기존 웹페이지 스크래핑 방식이 막혔으므로, WAF 우회가 지속적으로 패치되는
    yt-dlp 라이브러리를 직접 활용하여 JSON 메타데이터와 스트림 URL을 획득합니다.
    """

    def __init__(self, channel_id: str, cookies: Optional[Dict[str, str]] = None):
        super().__init__(channel_id, cookies)
        self.stream_url = None

    async def _extract_with_ytdlp(self) -> dict:
        def extract():
            ydl_opts = {
                'quiet': True,
                'simulate': True,
                'no_warnings': True,
                'extract_flat': False
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    return ydl.extract_info(f"https://www.tiktok.com/@{self.channel_id}/live", download=False)
                except Exception as e:
                    logger.debug(f"[TikTok] yt-dlp 추출 실패 ({self.channel_id}): {e}")
                    return None
        return await asyncio.to_thread(extract)

    async def is_live(self) -> bool:
        """TikTok 라이브 방송 중인지 확인합니다."""
        info = await self._extract_with_ytdlp()
        if info and info.get("is_live"):
            self.stream_url = info.get("url")
            return True
        return False

    async def get_metadata(self) -> Dict[str, Any]:
        """
        TikTok 라이브 스트림 메타데이터를 반환합니다.
        """
        info = await self._extract_with_ytdlp()
        if not info or not info.get("is_live"):
            return {"status": "CLOSE", "channel_name": self.channel_id}
            
        self.stream_url = info.get("url")
            
        return {
            "status": "OPEN",
            "title": info.get("title", f"{self.channel_id} TikTok Live"),
            "channel_name": info.get("uploader") or self.channel_id,
            "nickname": info.get("uploader", self.channel_id),
            "stream_url": self.stream_url,
            "thumbnail_url": info.get("thumbnail", ""),
            "viewer_count": info.get("view_count", 0),
        }

    async def get_channel_info(self) -> Dict[str, Any]:
        """채널 정보를 반환합니다."""
        info = await self._extract_with_ytdlp()
        if info:
            return {
                "channel_name": info.get("uploader") or self.channel_id,
                "nickname": info.get("uploader", self.channel_id),
            }
        return {"channel_name": self.channel_id}

    def get_streamlink_args(self) -> list:
        return []
    
    def get_download_url(self) -> Optional[str]:
        """라이브 스트림 URL을 반환합니다 (직접 다운로드용)."""
        if self.stream_url:
            return self.stream_url
            
        import asyncio
        import concurrent.futures
        
        async def _get():
            meta = await self.get_metadata()
            return meta.get("stream_url", "")
            
        try:
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _get())
                return future.result(timeout=10)
        except RuntimeError:
            return asyncio.run(_get())
        except Exception:
            return None
