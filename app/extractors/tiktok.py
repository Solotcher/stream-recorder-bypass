import asyncio
import json
from typing import Dict, Any, Optional
from app.extractors.base_extractor import BaseExtractor
from app.core.logger import logger


class TikTokExtractor(BaseExtractor):
    """
    TikTok Live 스트림 추출기.
    
    TikTok은 Streamlink를 지원하지 않으므로 직접 HTTP API로 라이브 상태를 확인하고,
    stream_url을 받아 직접 다운로드(httpx/aiohttp)합니다.
    TikTok의 WAF 우회를 위해 Browser-Version 헤더를 사용합니다.
    """
    
    # TikTok Webcast API endpoints
    WEBCAST_BASE = "https://webcast.tiktok.com/webcast"
    CHECK_ALIVE_URL = "https://tiktok.bullishye.com/api/room/check"
    
    # 기본 헤더 (브라우저 모방)
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.tiktok.com/",
        "Origin": "https://www.tiktok.com",
    }

    def __init__(self, channel_id: str, cookies: Optional[Dict[str, str]] = None):
        super().__init__(channel_id, cookies)
        # TikTok 특화 헤더로 업데이트
        self.headers = self.DEFAULT_HEADERS.copy()
        self.room_id: Optional[str] = None

    async def _get_room_info(self) -> dict:
        """
        TikTok 웹페이지 스크래핑을 통해 room_id와 status를 반환합니다.
        (Michele0303 방식: SIGI_STATE 파싱)
        """
        import re
        import json
        import aiohttp
        
        if getattr(self, 'room_id', None) and getattr(self, "status", 0) == 2:
            return {"roomId": self.room_id, "status": self.status}
            
        url = f"https://www.tiktok.com/@{self.channel_id}/live"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as resp:
                    html = await resp.text()
                    
            match = re.search(r'<script id="SIGI_STATE" type="application/json">(.*?)</script>', html, re.DOTALL)
            if not match:
                logger.warning(f"[TikTok] SIGI_STATE 미발견 ({self.channel_id})")
                return {}
                
            sigi = json.loads(match.group(1))
            user_info = sigi.get("LiveRoom", {}).get("liveRoomUserInfo", {}).get("user", {})
            room_id = str(user_info.get("roomId", "0"))
            status = user_info.get("status", 0)
            
            if room_id and room_id != "0":
                self.room_id = room_id
                self.status = status
                logger.debug(f"[TikTok] {self.channel_id} -> Room ID: {self.room_id}, Status: {status}")
                return {"roomId": room_id, "status": status}
        except Exception as e:
            logger.error(f"[TikTok] 채널 페이지 스크래핑 실패 ({self.channel_id}): {e}")
            
        return {}

    async def _get_room_id(self) -> Optional[str]:
        """ 호환성을 위해 유지하는 room_id 래퍼 메서드 """
        info = await self._get_room_info()
        room_id = info.get("roomId", "0")
        return room_id if room_id != "0" else None

    async def is_live(self) -> bool:
        """TikTok 라이브 방송 중인지 확인합니다."""
        info = await self._get_room_info()
        status = info.get("status", 0)
        
        if status == 2:
            return True
            
        # 이미 녹화 중이면 라이브 상태 보존
        try:
            from app.services.recorder import RecorderManager
            recorder = RecorderManager.get_instance(self.channel_id)
            if recorder.is_recording:
                logger.warning(f"[TikTok][{self.channel_id}] 녹화 중이므로 라이브 상태 임시 보존")
                return True
        except Exception:
            pass
            
        return False

    async def get_metadata(self) -> Dict[str, Any]:
        """
        TikTok 라이브 스트림 메타데이터를 반환합니다.
        Expected keys: 'title', 'channel_name', 'start_time', 'thumbnail_url', 'stream_url'
        """
        room_id = await self._get_room_id()
        if not room_id:
            return {"status": "CLOSE", "channel_name": self.channel_id}
        
        # 라이브 정보 조회
        url = f"{self.WEBCAST_BASE}/room/info/?aid=1988&room_id={room_id}&user_is_login=false"
        
        try:
            data = await self._fetch_json(url)
            room_data = data.get("data", {})
            
            if not room_data:
                return {"status": "CLOSE", "channel_name": self.channel_id}
            
            # TikTok 라이브 상태: status=2가 라이브
            is_live = room_data.get("status") == 2
            
            # Stream URL 가져오기 (FLV 스트림)
            stream_url = ""
            live_stream = room_data.get("live_stream", {})
            if live_stream:
                stream_url = live_stream.get("stream_url", {}).get("main", "")
                if not stream_url:
                    stream_url = live_stream.get("stream_url", {}).get("flv", "")
            
            # 오너 정보
            owner = room_data.get("owner", {})
            
            return {
                "title": room_data.get("title", "TikTok Live") or "TikTok Live",
                "channel_name": owner.get("display_id", self.channel_id) or self.channel_id,
                "nickname": owner.get("nickname", ""),
                "status": "OPEN" if is_live else "CLOSE",
                "stream_url": stream_url,
                "room_id": room_id,
                "thumbnail_url": room_data.get("cover_url", ""),
                "viewer_count": room_data.get("viewer_count", 0),
            }
            
        except Exception as e:
            logger.error(f"[TikTok] 메타데이터 조회 실패 ({self.channel_id}): {e}")
            return {"status": "ERROR", "channel_name": self.channel_id}

    async def get_channel_info(self) -> Dict[str, Any]:
        """채널 정보를 반환합니다 (라이브 여부와 무관)."""
        room_id = await self._get_room_id()
        
        if not room_id:
            return {"channel_name": self.channel_id}
        
        url = f"{self.WEBCAST_BASE}/room/info/?aid=1988&room_id={room_id}&user_is_login=false"
        
        try:
            data = await self._fetch_json(url)
            room_data = data.get("data", {})
            if room_data:
                owner = room_data.get("owner", {})
                return {
                    "channel_name": owner.get("display_id", self.channel_id) or self.channel_id,
                    "nickname": owner.get("nickname", ""),
                }
        except Exception as e:
            logger.error(f"[TikTok] 채널 정보 조회 실패: {e}")
            
        return {"channel_name": self.channel_id}

    def get_streamlink_args(self) -> list:
        """
        TikTok은 Streamlink를 사용하지 않습니다.
        빈 리스트를 반환하고, 녹화는 직접 HTTP 다운로드로 처리됩니다.
        """
        return []
    
    def get_download_url(self) -> Optional[str]:
        """라이브 스트림 URL을 반환합니다 (직접 다운로드용)."""
        import asyncio
        
        async def _get():
            meta = await self.get_metadata()
            return meta.get("stream_url", "")
        
        # 동기 컨텍스트에서 호출될 수 있으므로 이벤트 루프 확인
        try:
            loop = asyncio.get_running_loop()
            # 이미 실행 중이면 새 루프 대신 현재 것 사용
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _get())
                return future.result(timeout=10)
        except RuntimeError:
            # 실행 중인 루프가 없으면 새로 생성
            return asyncio.run(_get())
        except Exception:
            return None
