import asyncio
import json
import os
from typing import Dict, Any, Optional
from app.extractors.base_extractor import BaseExtractor
from app.core.config import settings
from app.core.logger import logger


class YouTubeExtractor(BaseExtractor):
    """
    유튜브 라이브 스트림 추출기.
    yt-dlp의 --dump-json 기능을 사용하여 API 키 없이 생방송 상태와 메타데이터를 조회합니다.
    녹화 시에는 Streamlink 대신 yt-dlp를 사용합니다.
    """

    # 채널 URL 패턴 (채널 ID 또는 핸들)
    CHANNEL_LIVE_URL = "https://www.youtube.com/channel/{}/live"
    HANDLE_LIVE_URL = "https://www.youtube.com/@{}/live"

    def __init__(self, channel_id: str, cookies: Optional[Dict[str, str]] = None):
        super().__init__(channel_id, cookies)
        # @핸들인지 채널 ID(UC로 시작)인지 판별하여 URL 결정
        self._is_handle = not channel_id.startswith("UC")

    def _get_live_url(self) -> str:
        """채널의 라이브 URL을 반환합니다."""
        if self._is_handle:
            return self.HANDLE_LIVE_URL.format(self.channel_id)
        return self.CHANNEL_LIVE_URL.format(self.channel_id)

    def _get_cookies_file_path(self) -> Optional[str]:
        """쿠키 딕셔너리를 Netscape 형식의 임시 쿠키 파일로 저장하고 경로를 반환합니다."""
        if not self.cookies:
            return None
        
        cookies_dir = os.path.join(settings.DATA_DIR)
        os.makedirs(cookies_dir, exist_ok=True)
        cookie_path = os.path.join(cookies_dir, "youtube_cookies.txt")
        
        try:
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write("# Netscape HTTP Cookie File\n")
                for name, value in self.cookies.items():
                    f.write(f".youtube.com\tTRUE\t/\tTRUE\t0\t{name}\t{value}\n")
            return cookie_path
        except Exception as e:
            logger.error(f"유튜브 쿠키 파일 생성 실패: {e}")
            return None

    async def _run_ytdlp_json(self, url: str) -> dict:
        """
        yt-dlp --dump-json을 실행하여 메타데이터를 JSON으로 반환합니다.
        라이브가 아닌 경우 빈 딕셔너리를 반환합니다.
        """
        import subprocess

        cmd = [
            settings.YTDLP_PATH,
            "--dump-json",
            "--no-download",
            "--no-playlist",
            "--socket-timeout", "15",
        ]

        cookie_file = self._get_cookies_file_path()
        if cookie_file:
            cmd.extend(["--cookies", cookie_file])

        # 유튜브 전용 또는 글로벌 프록시 적용
        proxy_url = settings.YOUTUBE_PROXY or settings.GLOBAL_PROXY
        if proxy_url:
            cmd.extend(["--proxy", proxy_url])

        # poToken 및 visitorData 우회 파라미터 적용
        ext_args = []
        if settings.YOUTUBE_PO_TOKEN:
            ext_args.append(f"po_token={settings.YOUTUBE_PO_TOKEN}")
        if settings.YOUTUBE_VISITOR_DATA:
            ext_args.append(f"visitor_data={settings.YOUTUBE_VISITOR_DATA}")
        if ext_args:
            cmd.extend(["--extractor-args", f"youtube:{';'.join(ext_args)}"])

        cmd.append(url)

        try:
            def _exec():
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout_data, stderr_data = proc.communicate(timeout=30)
                return proc.returncode, stdout_data, stderr_data

            returncode, stdout_bytes, stderr_bytes = await asyncio.to_thread(_exec)

            if returncode == 0 and stdout_bytes:
                return json.loads(stdout_bytes.decode("utf-8", errors="replace"))
            else:
                stderr_text = stderr_bytes.decode("utf-8", errors="replace")[-500:] if stderr_bytes else ""
                if "is not a video" not in stderr_text and "is offline" not in stderr_text:
                    logger.debug(f"yt-dlp 메타데이터 조회 실패 (code={returncode}): {stderr_text}")
        except asyncio.TimeoutError:
            logger.warning(f"yt-dlp --dump-json 타임아웃: {url}")
        except json.JSONDecodeError as e:
            logger.warning(f"yt-dlp JSON 파싱 실패: {e}")
        except Exception as e:
            logger.error(f"yt-dlp 메타데이터 조회 중 예외: {e}")

        return {}

    async def is_live(self) -> bool:
        """유튜브 채널이 현재 생방송 중인지 확인합니다 (초경량 HTML 파싱 선감지 적용)."""
        url = self._get_live_url()
        
        headers = self.headers.copy()
        import random
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0"
        ]
        headers["User-Agent"] = random.choice(user_agents)
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        headers["Accept-Language"] = "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
        
        cookie_str = self.get_cookie_string()
        if cookie_str:
            headers["Cookie"] = cookie_str
            
        proxy_url = settings.YOUTUBE_PROXY or settings.GLOBAL_PROXY or None
        
        try:
            # 유튜브 생방송 페이지 HTML 비동기 초경량 조회
            html = await self._fetch_text(url, headers=headers, timeout=10, proxy=proxy_url)
            if html:
                # 생방송 활성화 판단 지표 검색 ("isLive":true)
                if '"isLive":true' in html or '"isLiveLiveStream":true' in html or '\"isLive\":true' in html:
                    logger.info(f"[YouTube] 초경량 HTML 조회 생방송 감지 성공 ({self.channel_id})")
                    return True
                
                logger.debug(f"[YouTube] 초경량 HTML 조회 결과: 오프라인 ({self.channel_id})")
                return False
        except Exception as e:
            logger.error(f"[YouTube] 초경량 HTML 조회 에러: {e} - yt-dlp로 폴백하여 교차 검증을 진행합니다.")

        # HTML 조회 실패/예외 발생 시 기존 yt-dlp 방식으로 2차 폴백 검증
        meta = await self._run_ytdlp_json(url)
        return meta.get("is_live", False) is True

    async def get_metadata(self) -> Dict[str, Any]:
        """방송 메타데이터를 반환합니다."""
        url = self._get_live_url()
        meta = await self._run_ytdlp_json(url)

        if not meta:
            return {"status": "CLOSE", "channel_name": self.channel_id}

        is_live = meta.get("is_live", False)
        channel_name = meta.get("channel", meta.get("uploader", self.channel_id))
        categories = meta.get("categories", [])
        category = categories[0] if categories else ""

        return {
            "title": meta.get("title", "제목 없음"),
            "channel_name": channel_name,
            "category": category,
            "status": "OPEN" if is_live else "CLOSE",
            "thumbnail": meta.get("thumbnail", ""),
            "stream_url": meta.get("webpage_url", url),
        }

    async def get_channel_info(self) -> Dict[str, Any]:
        """채널 고유 정보를 반환합니다."""
        url = self._get_live_url()
        meta = await self._run_ytdlp_json(url)

        channel_name = self.channel_id
        if meta:
            channel_name = meta.get("channel", meta.get("uploader", self.channel_id))

        return {"channel_name": channel_name}

    def get_streamlink_args(self) -> list:
        """
        유튜브는 yt-dlp를 사용하므로 이 메서드는 yt-dlp 전용 인자를 반환합니다.
        scheduler의 trigger_recording에서 유튜브 분기로 처리됩니다.
        """
        args = [
            "--no-part",
            "--no-playlist",
            "--socket-timeout", "15",
            "--retries", "10",
            "--fragment-retries", "10",
            # 라이브 전용
            "--live-from-start",
            "--wait-for-video", "30-120",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
            "--merge-output-format", "mp4",
        ]

        # 유튜브 전용 또는 글로벌 프록시 적용
        proxy_url = settings.YOUTUBE_PROXY or settings.GLOBAL_PROXY
        if proxy_url:
            args.extend(["--proxy", proxy_url])

        # poToken 및 visitorData 우회 파라미터 적용
        ext_args = []
        if settings.YOUTUBE_PO_TOKEN:
            ext_args.append(f"po_token={settings.YOUTUBE_PO_TOKEN}")
        if settings.YOUTUBE_VISITOR_DATA:
            ext_args.append(f"visitor_data={settings.YOUTUBE_VISITOR_DATA}")
        if ext_args:
            args.extend(["--extractor-args", f"youtube:{';'.join(ext_args)}"])

        cookie_file = self._get_cookies_file_path()
        if cookie_file:
            args.extend(["--cookies", cookie_file])

        return args

