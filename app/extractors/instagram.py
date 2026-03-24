import asyncio
import json
from typing import Dict, Any, Optional
from app.extractors.base_extractor import BaseExtractor
from app.core.logger import logger

class InstagramExtractor(BaseExtractor):
    """
    Instagram Live 스트림 추출기.
    인스타그램 비공식 API를 사용하며 sessionid 쿠키가 필수입니다.
    """
    
    def __init__(self, channel_id: str, cookies: Optional[Dict[str, str]] = None):
        super().__init__(channel_id, cookies)
        self.headers.update({
            "User-Agent": "Instagram 219.0.0.12.117 Android",
            "Accept-Language": "en-US",
            "X-IG-App-ID": "936619743392459",
            "X-IG-Connection-Type": "WIFI",
        })
        self.user_id = None

    async def _get_user_id(self) -> str:
        if self.user_id:
            return self.user_id
            
        url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={self.channel_id}"
        web_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "X-IG-App-ID": "936619743392459",
        }
        if self.cookies:
            web_headers["Cookie"] = self.get_cookie_string()
            
        data = await self._fetch_json(url, headers=web_headers)
        if data and "data" in data and data["data"].get("user"):
            self.user_id = data["data"]["user"]["id"]
            return self.user_id
        return ""

    async def _get_broadcast_info(self) -> dict:
        uid = await self._get_user_id()
        if not uid:
            return {}
            
        headers = self.headers.copy()
        if self.cookies:
            headers["Cookie"] = self.get_cookie_string()
            
        url = f"https://i.instagram.com/api/v1/feed/user/{uid}/story/"
        data = await self._fetch_json(url, headers=headers)
        
        if not data:
            return {}
            
        if "broadcast" in data and data["broadcast"]:
            return data["broadcast"]
            
        return {}

    async def is_live(self) -> bool:
        broadcast = await self._get_broadcast_info()
        return bool(broadcast and broadcast.get("broadcast_status") == "active")

    async def get_metadata(self) -> Dict[str, Any]:
        if not self.cookies or "sessionid" not in self.cookies:
            logger.warning(f"[Instagram] {self.channel_id} 조회를 위해 sessionid 쿠키가 필요합니다.")
            return {"status": "CLOSE", "channel_name": self.channel_id}
            
        broadcast = await self._get_broadcast_info()
        if not broadcast or broadcast.get("broadcast_status") != "active":
            return {"status": "CLOSE", "channel_name": self.channel_id}
            
        owner = broadcast.get("broadcast_owner", {})
        channel_name = owner.get("username", self.channel_id)
        
        stream_url = broadcast.get("dash_abr_playback_url") or broadcast.get("dash_playback_url") or ""
        
        return {
            "title": f"Instagram Live - {channel_name}",
            "channel_name": channel_name,
            "status": "OPEN",
            "stream_url": stream_url,
            "thumbnail_url": broadcast.get("cover_frame_url", ""),
            "viewer_count": broadcast.get("viewer_count", 0),
        }

    async def get_channel_info(self) -> Dict[str, Any]:
        return {"channel_name": self.channel_id}

    def get_streamlink_args(self) -> list:
        args = [
            "--stream-segment-timeout", "15",
            "--stream-timeout", "30",
        ]
        cookie_str = self.get_cookie_string()
        if cookie_str:
            args.extend(["--http-header", f"Cookie={cookie_str}"])
        return args
