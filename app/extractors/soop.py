import re
from typing import Dict, Any, Optional
from app.extractors.base_extractor import BaseExtractor
from app.core.logger import logger

class SoopExtractor(BaseExtractor):
    """
    숲(SOOP) FHD 자동 녹화를 위한 모듈. 
    URL 입력을 자동으로 분석하여 LIVE와 VOD를 식별합니다.
    일반적인 m3u8 방식 외에, soop-streamer-alert처럼 웹소켓 및 chunk 다운로드 병합 방식을 
    옵셔널하게 선택할 수 있도록 구현.
    """
    
    BASE_API_URL = "https://live.sooplive.co.kr/afreeca/player_live_api.php"

    def __init__(self, channel_id_or_url: str, cookies: Optional[Dict[str, str]] = None):
        super().__init__(channel_id_or_url, cookies)
        
        # 1. 입력받은 문자열이 URL인지 ID인지 판단하여 분류합니다.
        self.stream_type, self.clean_id = self._parse_target(channel_id_or_url)
        
        # 2. 부모 클래스에서 저장한 channel_id를 순수 ID로 덮어씌웁니다.
        self.channel_id = self.clean_id 

    def _parse_target(self, target: str) -> tuple[str, str]:
        """ 주소 또는 ID를 분석하여 (타입, 순수ID)를 반환합니다. """
        
        # VOD 패턴 검사 (예: vod.sooplive.com/player/12345, /vods/12345)
        vod_match = re.search(r'(?:vod\.sooplive\.(?:co\.kr|com)/player/|/vods?/|/vod/)(\d+)', target)
        if vod_match:
            return "VOD", vod_match.group(1)
        
        # Live 패턴 검사 (예: play.sooplive.co.kr/bjid, station/bjid)
        live_match = re.search(r'(?:ch\.sooplive\.(?:co\.kr|com)/|play\.sooplive\.(?:co\.kr|com)/|sooplive\.(?:co\.kr|com)/|station/)(\w+)', target)
        if live_match:
            return "LIVE", live_match.group(1)
            
        # URL 형태가 아닌 단순 문자열일 경우 기본적으로 LIVE ID로 간주합니다.
        if not target.startswith("http"):
            return "LIVE", target
            
        return "UNKNOWN", target

    async def get_metadata(self) -> Dict[str, Any]:
        """ SOOP 방송국 정보 API를 통한 메타데이터 조회 """
        
        # VOD인 경우 Live API를 찌를 필요 없이 즉시 VOD 메타데이터를 반환합니다.
        if self.stream_type == "VOD":
            return {
                "title": f"VOD 영상 ({self.clean_id})",
                "channel_name": self.clean_id,
                "category": "VOD",
                "status": "VOD", # 상태를 OPEN/CLOSE가 아닌 VOD로 명시하여 라이브와 구분
                "stream_url": f"https://vod.sooplive.co.kr/player/{self.clean_id}"
            }

        url = self.BASE_API_URL
        
        try:
            req_headers = self.headers.copy()
            req_headers["Origin"] = "https://play.sooplive.co.kr"
            req_headers["Referer"] = "https://play.sooplive.co.kr/"
            req_headers["Content-Type"] = "application/x-www-form-urlencoded"
            
            payload = f"bid={self.channel_id}"
            
            data = await self._fetch_json(url, method="POST", headers=req_headers, data=payload, timeout=10)
            
            if not data:
                logger.warning(f"SOOP API 응답 없음: {self.channel_id}")
                return {"status": "ERROR"}
            
            channel = data.get("CHANNEL")
            
            if not channel:
                logger.warning(f"SOOP API CHANNEL 응답 누락: {self.channel_id}")
                return {"status": "ERROR"}
                
            is_live = (channel.get("RESULT") == 1)
            
            if not is_live:
                return {"status": "CLOSE"}
                
            return {
                "title": channel.get("TITLE", "제목 없음"),
                "channel_name": channel.get("BJNICK", self.channel_id),
                "category": channel.get("CATE", ""),
                "status": "OPEN", 
                "stream_url": f"https://play.sooplive.co.kr/{self.channel_id}"
            }
        except Exception as e:
            logger.error(f"SOOP API 통신 실패: {str(e)}")
            return {"status": "ERROR"}

    async def get_channel_info(self) -> Dict[str, Any]:
        """ SOOP 플레이어 API를 재활용하여 라이브 관계없이 닉네임 파싱 시도 """
        
        # VOD인 경우 채널명 조회 로직을 스킵하고 ID를 그대로 반환하거나 VOD API를 따로 찌르도록 처리할 수 있습니다.
        if self.stream_type == "VOD":
            return {"channel_name": self.channel_id}

        url = self.BASE_API_URL
        try:
            req_headers = self.headers.copy()
            req_headers["Origin"] = "https://play.sooplive.co.kr"
            req_headers["Referer"] = "https://play.sooplive.co.kr/"
            req_headers["Content-Type"] = "application/x-www-form-urlencoded"
            
            payload = f"bid={self.channel_id}"
            
            data = await self._fetch_json(url, method="POST", headers=req_headers, data=payload, timeout=10)
            if data:
                channel = data.get("CHANNEL")
                if channel:
                    return {"channel_name": channel.get("BJNICK", self.channel_id)}
        except Exception as e:
            logger.error(f"SOOP API 통신 실패 (채널조회): {str(e)}")
            
        return {"channel_name": self.channel_id}

    async def is_live(self) -> bool:
        meta = await self.get_metadata()
        
        # VOD 타입인 경우 생방송이 아니므로 False를 반환하여 메인 로직에서 VOD 다운로드로 넘어가게 유도
        if meta.get("status") == "VOD":
            return False

        if meta.get("status") == "ERROR":
            # API 일시 오류 시: 이미 녹화가 진행 중이면 True(세션 보존), 아니면 False(새 녹화 시도 안 함)
            from app.services.recorder import RecorderManager
            recorder = RecorderManager.get_instance(self.channel_id)
            if recorder.is_recording:
                logger.warning(f"[{self.channel_id}] API 오류이나 녹화 중이므로 라이브 상태를 보존합니다.")
                return True
            logger.warning(f"[{self.channel_id}] API 오류. 녹화 중이 아니므로 라이브 판단을 보류합니다.")
            return False
        return meta.get("status") == "OPEN"

    def get_streamlink_args(self) -> list:
        """
        SOOP 녹화용 Streamlink 인자.
        Streamlink soop 플러그인의 title-change 이슈(GitHub #6703) 대응으로
        --hls-live-reload, --retry-open 플래그를 포함하여 즉시 종료를 방지합니다.
        """
        args = [
            "--stream-segment-timeout", "30",
            "--stream-timeout", "120",
            "--retry-streams", "10",
            "--retry-open", "5",
            "--hls-live-restart",
            "--hls-segment-stream-data",
            "--http-header", "Origin=https://play.sooplive.co.kr",
            "--http-header", "Referer=https://play.sooplive.co.kr/"
        ]
        cookie_str = self.get_cookie_string()
        if cookie_str:
            args.extend(["--http-header", f"Cookie={cookie_str}"])
            
        # 수동 녹화 등으로 주입된 일회성 비밀번호 처리
        stream_pw = getattr(self, "stream_password", None)
        if stream_pw:
            args.extend(["--soop-stream-password", stream_pw])
            
        return args