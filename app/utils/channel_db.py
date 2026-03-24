"""
채널 데이터 접근을 캡슐화하는 Repository 패턴 모듈.

기존 channel_db.py의 5개 함수에서 반복되던 SessionLocal() 보일러플레이트와
_to_dict 변환 로직의 중복을 제거합니다.

사용법:
    repo = ChannelRepository()
    channels = repo.get_all()
    channel = repo.get_by_id("channel_id")
"""
from contextlib import contextmanager
from typing import List, Dict, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.logger import logger
from app.db.session import SessionLocal
from app.db.models import Channel


class ChannelRepository:
    """채널 DB 접근을 캡슐화하는 Repository 클래스"""

    @staticmethod
    @contextmanager
    def _get_session():
        """DB 세션 생명주기를 관리하는 컨텍스트 매니저"""
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    def _to_dict(channel: Channel) -> Dict:
        """Channel ORM 모델을 딕셔너리로 변환"""
        return {
            "id": channel.id,
            "platform": channel.platform,
            "name": channel.name,
            "resolution": channel.resolution,
            "is_active": channel.is_active,
        }

    def get_all(self) -> List[Dict]:
        """등록된 모든 채널 목록을 조회합니다."""
        with self._get_session() as db:
            try:
                stmt = select(Channel)
                channels = db.execute(stmt).scalars().all()
                return [self._to_dict(c) for c in channels]
            except Exception as e:
                logger.error(f"채널 DB 조회 중 에러 발생: {e}")
                return []

    def get_by_id(self, channel_id: str) -> Optional[Dict]:
        """특정 채널 정보를 ID로 조회합니다."""
        with self._get_session() as db:
            stmt = select(Channel).where(Channel.id == channel_id)
            c = db.execute(stmt).scalars().first()
            return self._to_dict(c) if c else None

    def add(self, channel_data: Dict) -> bool:
        """새 채널을 등록합니다."""
        with self._get_session() as db:
            try:
                new_ch = Channel(
                    id=channel_data.get("id"),
                    platform=channel_data.get("platform", "unknown"),
                    name=channel_data.get("name", channel_data.get("id")),
                    resolution=channel_data.get("resolution", "best"),
                    is_active=channel_data.get("is_active", True),
                )
                db.add(new_ch)
                db.commit()
                logger.info(f"채널 추가 완료: {new_ch.name}")
                return True
            except IntegrityError:
                db.rollback()
                logger.warning(f"이미 존재하는 채널입니다: {channel_data.get('id')}")
                return False
            except Exception as e:
                db.rollback()
                logger.error(f"채널 추가 실패: {e}")
                return False

    def update(self, channel_id: str, updated_data: Dict) -> bool:
        """채널 정보를 업데이트합니다."""
        with self._get_session() as db:
            try:
                stmt = select(Channel).where(Channel.id == channel_id)
                c = db.execute(stmt).scalars().first()
                if not c:
                    return False

                for key, value in updated_data.items():
                    if hasattr(c, key):
                        setattr(c, key, value)

                db.commit()
                return True
            except Exception as e:
                db.rollback()
                logger.error(f"채널 업데이트 실패: {e}")
                return False

    def delete(self, channel_id: str) -> bool:
        """채널을 삭제합니다."""
        with self._get_session() as db:
            try:
                stmt = select(Channel).where(Channel.id == channel_id)
                c = db.execute(stmt).scalars().first()
                if c:
                    db.delete(c)
                    db.commit()
                    logger.info(f"채널 삭제 완료: {channel_id}")
                    return True
                return False
            except Exception as e:
                db.rollback()
                logger.error(f"채널 삭제 실패: {e}")
                return False


# 글로벌 싱글턴 인스턴스 — 기존 함수형 API와 동일한 인터페이스 제공
_repo = ChannelRepository()


def get_all_channels() -> List[Dict]:
    """하위 호환용 래퍼: channel_db.get_all_channels()"""
    return _repo.get_all()


def get_channel(channel_id: str) -> Optional[Dict]:
    """하위 호환용 래퍼: channel_db.get_channel()"""
    return _repo.get_by_id(channel_id)


def add_channel(channel_data: Dict) -> bool:
    """하위 호환용 래퍼: channel_db.add_channel()"""
    return _repo.add(channel_data)


def update_channel(channel_id: str, updated_data: Dict) -> bool:
    """하위 호환용 래퍼: channel_db.update_channel()"""
    return _repo.update(channel_id, updated_data)


def delete_channel(channel_id: str) -> bool:
    """하위 호환용 래퍼: channel_db.delete_channel()"""
    return _repo.delete(channel_id)


def init_db_if_not_exists():
    """DB 초기화 호출 (기존 호환)"""
    from app.db.session import init_db
    init_db()
