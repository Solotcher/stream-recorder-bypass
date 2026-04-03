from sqlalchemy import Column, String, Boolean, DateTime, Integer
from app.db.session import Base

class Channel(Base):
    __tablename__ = "channels"

    id = Column(String, primary_key=True, index=True, doc="플랫폼별 스트리머 고유 ID (예: 111111 등)")
    platform = Column(String, nullable=False, doc="chzzk, twitch, soop 등")
    name = Column(String, nullable=False, doc="스트리머 표시 닉네임")
    resolution = Column(String, default="best", doc="녹화 화질 선호도")
    is_active = Column(Boolean, default=True, doc="True일 때만 스케줄러가 모니터링 수행")

class ActiveSession(Base):
    __tablename__ = "active_sessions"
    
    channel_id = Column(String, primary_key=True)
    platform = Column(String, nullable=False)
    channel_name = Column(String, nullable=False)
    title = Column(String, default="")
    category = Column(String, default="")
    record_type = Column(String, default="scheduled")
    started_at = Column(DateTime, nullable=True)
    part = Column(Integer, default=0)

