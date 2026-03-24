import os
from typing import List, Dict, Optional
from app.core.logger import logger
from app.db.session import SessionLocal, init_db
from app.db.models import Channel
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

# FastAPI 시작 시 초기화하기 위해 호출될 여지를 남겨둠
def init_db_if_not_exists():
    init_db()

def get_all_channels() -> List[Dict]:
    db = SessionLocal()
    try:
        # SQLAlchemy 2.0 style
        stmt = select(Channel)
        channels = db.execute(stmt).scalars().all()
        return [
            {
                "id": c.id,
                "platform": c.platform,
                "name": c.name,
                "resolution": c.resolution,
                "is_active": c.is_active
            }
            for c in channels
        ]
    except Exception as e:
        logger.error(f"채널 DB 조회 중 에러 발생: {e}")
        return []
    finally:
        db.close()

def get_channel(channel_id: str) -> Optional[Dict]:
    db = SessionLocal()
    try:
        stmt = select(Channel).where(Channel.id == channel_id)
        c = db.execute(stmt).scalars().first()
        if c:
            return {
                "id": c.id,
                "platform": c.platform,
                "name": c.name,
                "resolution": c.resolution,
                "is_active": c.is_active
            }
        return None
    finally:
        db.close()

def add_channel(channel_data: Dict) -> bool:
    db = SessionLocal()
    try:
        new_ch = Channel(
            id=channel_data.get("id"),
            platform=channel_data.get("platform", "unknown"),
            name=channel_data.get("name", channel_data.get("id")),
            resolution=channel_data.get("resolution", "best"),
            is_active=channel_data.get("is_active", True)
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
    finally:
        db.close()

def update_channel(channel_id: str, updated_data: Dict) -> bool:
    db = SessionLocal()
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
    finally:
        db.close()

def delete_channel(channel_id: str) -> bool:
    db = SessionLocal()
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
    finally:
        db.close()
