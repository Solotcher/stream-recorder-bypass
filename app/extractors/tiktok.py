import asyncio
from typing import Dict, Any, Optional
from app.extractors.base_extractor import BaseExtractor
from app.core.logger import logger
import yt_dlp

class TikTokExtractor(BaseExtractor):
    """
    TikTok Live 스트림 추출기.
    yt-dlp 라이브러리를 활용하여 JSON 메타데이터와 스트림 URL을 획득하며, 
    최신 WAF 우회 및 비동기 환경 충돌 방지 로직이 적용되어 있습니다.
    """

    def __init__(self, channel_id: str, cookies: Optional[Dict[str, str]] = None):
        super().__init__(channel_id, cookies)
        self.stream_url = None
        self._cached_info = None

    def _get_cookies_file_path(self) -> Optional[str]:
        if not self.cookies:
            return None
        import os
        from app.core.config import settings
        cookies_dir = settings.DATA_DIR
        os.makedirs(cookies_dir, exist_ok=True)
        cookie_path = os.path.join(cookies_dir, "tiktok_cookies.txt")
        with open(cookie_path, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            for name, value in self.cookies.items():
                f.write(f".tiktok.com\tTRUE\t/\tTRUE\t0\t{name}\t{value}\n")
        return cookie_path

    async def _extract_with_ytdlp(self) -> dict:
        def extract():
            # [수정됨] 틱톡 봇 차단을 우회하고 HLS 404 에러를 피하기 위한 최신 옵션
            ydl_opts = {
                'quiet': True,
                'simulate': True,
                'no_warnings': True,
                'extract_flat': False,
                'format': 'best[ext=flv]/best', # HLS 오류 우회를 위해 FLV 포맷 강제 우선 적용
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                }
            }
            cookie_file = self._get_cookies_file_path()
            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    return ydl.extract_info(f"https://www.tiktok.com/@{self.channel_id}/live", download=False)
                except Exception as e:
                    logger.debug(f"[TikTok] yt-dlp 추출 실패 ({self.channel_id}): {e}")
                    return None
        return await asyncio.to_thread(extract)

    async def is_live(self) -> bool:
        self._cached_info = await self._extract_with_ytdlp()
        if self._cached_info and self._cached_info.get("is_live"):
            self.stream_url = self._cached_info.get("url")
            return True
        self._cached_info = None
        return False

    async def get_metadata(self) -> Dict[str, Any]:
        info = self._cached_info or await self._extract_with_ytdlp()
        self._cached_info = None 
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
        info = await self._extract_with_ytdlp()
        if info:
            return {
                "channel_name": info.get("uploader") or self.channel_id,
                "nickname": info.get("uploader", self.channel_id),
            }
        return {"channel_name": self.channel_id}

    def get_streamlink_args(self) -> list:
        args = ["--no-playlist", "--socket-timeout", "15", "--retries", "10"]
        cookie_file = self._get_cookies_file_path()
        if cookie_file:
            args.extend(["--cookies", cookie_file])
        return args
    
    # [수정됨] RuntimeError 방지를 위해 비동기(async) 함수로 변경 및 로직 간소화
    async def get_download_url(self) -> Optional[str]:
        """라이브 스트림 URL을 반환합니다 (비동기 환경 대응)."""
        if self.stream_url:
            return self.stream_url
            
        try:
            meta = await self.get_metadata()
            return meta.get("stream_url", None)
        except Exception as e:
            logger.debug(f"[TikTok] download_url 추출 실패: {e}")
            return None