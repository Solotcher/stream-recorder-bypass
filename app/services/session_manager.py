"""
녹화 세션의 생명주기를 관리하는 전담 서비스.
RecorderManager의 session_* 속성들을 SessionManager로 이관하여 SRP를 준수합니다.

RecorderManager는 프로세스 관리(PID, is_recording)만 담당하고,
SessionManager는 세션 메타데이터(started_at, part, platform 등) 관리를 전담합니다.
"""
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class RecordingSession:
    """단일 녹화 세션의 상태를 표현하는 데이터 클래스"""
    channel_id: str
    platform: str
    channel_name: str
    title: str = ""
    category: str = ""
    record_type: str = "scheduled"
    started_at: Optional[datetime] = None
    part: int = 0


class SessionManager:
    """채널별 녹화 세션을 추적·관리하는 싱글턴 서비스"""

    _sessions: Dict[str, RecordingSession] = {}

    @classmethod
    def start_session(
        cls,
        channel_id: str,
        platform: str,
        channel_name: str,
        meta: Dict[str, Any],
        record_type: str = "scheduled"
    ) -> RecordingSession:
        """
        새 세션을 시작하거나, 기존 세션의 파트를 증가시킵니다.

        Returns:
            현재 활성 세션 객체
        """
        if channel_id not in cls._sessions:
            session = RecordingSession(
                channel_id=channel_id,
                platform=platform,
                channel_name=channel_name,
                title=meta.get("title", ""),
                category=meta.get("category", ""),
                record_type=record_type,
                started_at=datetime.now(),
                part=1,
            )
            cls._sessions[channel_id] = session
        else:
            session = cls._sessions[channel_id]
            session.part += 1
            # 메타데이터 갱신 (방송 제목은 파트마다 바뀔 수 있음)
            session.title = meta.get("title", session.title)
            session.category = meta.get("category", session.category)

        return session

    @classmethod
    def end_session(cls, channel_id: str) -> Optional[RecordingSession]:
        """세션을 종료하고 제거합니다. 종료된 세션 정보를 반환합니다."""
        return cls._sessions.pop(channel_id, None)

    @classmethod
    def get_session(cls, channel_id: str) -> Optional[RecordingSession]:
        """현재 활성 세션을 조회합니다."""
        return cls._sessions.get(channel_id)

    @classmethod
    def get_all_active_sessions(cls) -> Dict[str, RecordingSession]:
        """모든 활성 세션 목록을 반환합니다. (API 응답용)"""
        return dict(cls._sessions)

    @classmethod
    def restore_session(
        cls,
        channel_id: str,
        platform: str,
        channel_name: str,
        title: str = "",
        record_type: str = "scheduled",
        part: int = 0
    ) -> RecordingSession:
        """서버 재시작 시 세션 상태를 복구합니다."""
        session = RecordingSession(
            channel_id=channel_id,
            platform=platform,
            channel_name=channel_name,
            title=title,
            record_type=record_type,
            started_at=datetime.now(),
            part=part,
        )
        cls._sessions[channel_id] = session
        return session
