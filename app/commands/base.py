"""
녹화 커맨드 빌더 추상 인터페이스.
각 플랫폼(Streamlink/yt-dlp)이 이 인터페이스를 구현합니다.
"""
from abc import ABC, abstractmethod
from typing import List, Optional


class CommandBuilder(ABC):
    """녹화 프로세스 실행을 위한 CLI 커맨드를 조립하는 추상 빌더"""

    @abstractmethod
    def build_command(
        self,
        stream_url: str,
        output_path: str,
        resolution: str = "best",
        extra_args: Optional[List[str]] = None
    ) -> List[str]:
        """
        플랫폼별 녹화 커맨드(리스트 형태)를 조립하여 반환.

        Args:
            stream_url: 스트림 원본 URL
            output_path: 녹화 파일 저장 절대 경로
            resolution: 화질 선호도 (best, 1080p60 등)
            extra_args: 추가 인자 (쿠키, 인증 헤더 등)

        Returns:
            subprocess.Popen에 전달할 커맨드 리스트
        """
        pass

    @abstractmethod
    def get_output_extension(self) -> str:
        """이 빌더가 생성하는 녹화 파일의 기본 확장자 (예: '.ts', '.mp4')"""
        pass

    @abstractmethod
    def needs_remuxing(self) -> bool:
        """녹화 완료 후 리먹싱(.ts → .mp4)이 필요한지 여부"""
        pass
