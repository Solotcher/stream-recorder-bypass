import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

# 데이터베이스 디렉토리 보장
DB_DIR = os.path.join(settings.BASE_DIR, "data")
os.makedirs(DB_DIR, exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{os.path.join(DB_DIR, 'stream_record.db')}"

# SQLite는 멀티 스레드 접속을 허용하려면 check_same_thread=False가 필요
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def init_db():
    import app.db.models
    Base.metadata.create_all(bind=engine)

def get_db():
    """ FastAPI Dependency Injection용 """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
