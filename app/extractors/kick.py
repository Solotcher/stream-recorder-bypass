import asyncio
from typing import Dict, Any, Optional
from app.extractors.base_extractor import BaseExtractor
from app.core.logger import logger
from app.core.config import settings
import yt_dlp

try:
    from curl_cffi.requests import AsyncSession
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    logger.warning("[Kick] curl_cffi 패키지가 없어 Cloudflare 우회 API 조회가 불가능합니다. yt-dlp로 폴백합니다.")

class KickExtractor(BaseExtractor):
    """
    Kick Live 스트림 추출기.
    
    Cloudflare Turnstile 방어벽을 우회하기 위해 curl_cffi의 Chrome TLS 위장을 사용하여
    초경량 API 조회를 수행하고, 실패 시 yt-dlp 기반 폴백 검증을 지원합니다.
    """

    def __init__(self, channel_id: str, cookies: Optional[Dict[str, str]] = None):
        super().__init__(channel_id, cookies)
        self._cached_info = None
        self.stream_url = None

    async def _fetch_via_curl_cffi(self) -> Optional[dict]:
        """curl_cffi를 활용해 Cloudflare를 우회하고 킥 공식 API 호출을 수행합니다."""
        if not CURL_CFFI_AVAILABLE:
            return None
            
        url = f"https://kick.com/api/v1/channels/{self.channel_id}"
        
        # 킥 전용 또는 글로벌 프록시 설정 적용
        proxy_url = getattr(settings, "GLOBAL_PROXY", "") or None
        
        try:
            async with AsyncSession() as s:
                # Chrome 110 지문 모사로 CF 방어선 돌파
                resp = await s.get(
                    url, 
                    impersonate="chrome110", 
                    timeout=10, 
                    proxy=proxy_url
                )
                
                if resp.status_code == 200:
                    return resp.json()
                else:
                    logger.warning(f"[Kick] API HTTP 에러 (status={resp.status_code})")
        except Exception as e:
            logger.error(f"[Kick] curl_cffi API 조회 실패: {e}")
            
        return None

    async def _extract_with_ytdlp(self) -> dict:
        """yt-dlp를 이용한 킥 채널 메타데이터 폴백 조회."""
        def extract():
            ydl_opts = {
                'quiet': True,
                'simulate': True,
                'no_warnings': True,
            }
            
            # 프록시 설정
            proxy_url = getattr(settings, "GLOBAL_PROXY", "")
            if proxy_url:
                ydl_opts['proxy'] = proxy_url
                
            cookie_str = self.get_cookie_string()
            if cookie_str:
                ydl_opts['http_headers'] = {
                    'Cookie': cookie_str,
                    'User-Agent': self.headers.get("User-Agent", ""),
                }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    return ydl.extract_info(f"https://kick.com/{self.channel_id}", download=False)
                except Exception as e:
                    logger.debug(f"[Kick] yt-dlp 추출 실패 ({self.channel_id}): {e}")
                    return None
        return await asyncio.to_thread(extract)

    async def is_live(self) -> bool:
        """현재 생방송 진행 여부 판별 (초경량 curl_cffi API 조회 우선 실행)."""
        # 1. 초경량 curl_cffi API 조회 시도
        api_data = await self._fetch_via_curl_cffi()
        if api_data:
            livestream = api_data.get("livestream")
            is_live_status = livestream is not None and livestream.get("is_live") is True
            
            if is_live_status:
                # HLS 스트림 URL 캐싱 및 메타데이터 캐싱 유도
                self.stream_url = api_data.get("playback_url") or livestream.get("playback_url")
                self._cached_info = {
                    "is_live": True,
                    "title": livestream.get("session_title", "제목 없음"),
                    "uploader": api_data.get("user", {}).get("username", self.channel_id),
                    "uploader_id": self.channel_id,
                    "thumbnail": livestream.get("thumbnail", {}).get("url", ""),
                    "view_count": livestream.get("viewer_count", 0),
                    "url": self.stream_url
                }
                logger.info(f"[Kick] curl_cffi API 초경량 조회 생방송 감지 성공 ({self.channel_id})")
                return True
            else:
                logger.debug(f"[Kick] curl_cffi API 초경량 조회 결과: 오프라인 ({self.channel_id})")
                self._cached_info = None
                self.stream_url = None
                return False
                
        # 2. curl_cffi API 실패 시 yt-dlp로 폴백 검증
        logger.warning(f"[Kick] curl_cffi API 실패로 yt-dlp 폴백 검증을 가동합니다 ({self.channel_id})")
        self._cached_info = await self._extract_with_ytdlp()
        if self._cached_info and self._cached_info.get("is_live"):
            self.stream_url = self._cached_info.get("url")
            return True
            
        self._cached_info = None
        self.stream_url = None
        return False

    async def get_metadata(self) -> Dict[str, Any]:
        """방송 메타데이터를 반환합니다."""
        info = self._cached_info or await self._extract_with_ytdlp()
        self._cached_info = None  # 캐시 소모 후 초기화
        
        if not info or not info.get("is_live"):
            return {"status": "CLOSE", "channel_name": self.channel_id}
            
        self.stream_url = info.get("url")
            
        return {
            "status": "OPEN",
            "title": info.get("title", f"{self.channel_id} Kick Live"),
            "channel_name": info.get("uploader_id") or info.get("uploader") or self.channel_id,
            "nickname": info.get("uploader", self.channel_id),
            "thumbnail_url": info.get("thumbnail", ""),
            "viewer_count": info.get("view_count", 0),
            "stream_url": self.stream_url or f"https://kick.com/{self.channel_id}",
        }

    async def get_channel_info(self) -> Dict[str, Any]:
        """채널 고유의 정보(예: 닉네임)를 조회합니다."""
        api_data = await self._fetch_via_curl_cffi()
        if api_data:
            user = api_data.get("user", {})
            username = user.get("username")
            if username:
                return {"channel_name": username}
                
        return {"channel_name": self.channel_id}

    def get_streamlink_args(self) -> list:
        """Kick 녹화용 Streamlink 부가 인자."""
        args = [
            "--hls-live-restart",
            "--stream-timeout", "60",
            "--retry-streams", "5",
        ]
        
        # 글로벌 프록시 적용
        proxy_url = getattr(settings, "GLOBAL_PROXY", "")
        if proxy_url:
            args.extend(["--proxy", proxy_url])
            
        return args
