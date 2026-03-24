import os
import json
import sys

# 프로젝트 최상단 경로를 sys.path에 추가하여 app 모듈 import 가능하게 함
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.config import settings
from app.db.session import init_db, SessionLocal
from app.db.models import Channel

def migrate():
    # 데이터베이스 테이블 생성
    init_db()
    
    # 기존 JSON 경로
    json_path = os.path.join(settings.BASE_DIR, "data", "channels.json")
    if not os.path.exists(json_path):
        print(f"⚠️ {json_path} 파일을 찾을 수 없습니다. 빈 DB로 시작합니다.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print("❌ JSON 파싱 에러. channels.json이 비어있거나 손상되었습니다.")
            return
            
    if not isinstance(data, list):
        print("❌ channels.json 포맷이 올바르지 않습니다 (리스트가 아님).")
        return

    db = SessionLocal()
    count = 0
    try:
        for ch in data:
            # 중복 체크
            existing = db.query(Channel).filter(Channel.id == ch.get("id")).first()
            if not existing:
                new_channel = Channel(
                    id=ch.get("id"),
                    platform=ch.get("platform", "unknown"),
                    name=ch.get("name", ch.get("id")),
                    resolution=ch.get("resolution", "best"),
                    is_active=ch.get("is_active", True)
                )
                db.add(new_channel)
                count += 1
        
        db.commit()
        print(f"✅ 마이그레이션 완료: 총 {count}개의 채널이 SQLite로 복사되었습니다.")
    except Exception as e:
        db.rollback()
        print(f"❌ 마이그레이션 중 오류 발생: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
