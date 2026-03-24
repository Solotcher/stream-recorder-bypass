import os
import shutil

src = ".env"
dest = os.path.join("data", ".env")

if os.path.exists(src):
    if os.path.isfile(src):
        os.makedirs("data", exist_ok=True)
        # 만약 data/.env가 없다면 복사
        if not os.path.exists(dest):
            shutil.copy(src, dest)
            print(f"Successfully migrated {src} to {dest}")
        # 복사 후 백업용 원본 삭제
        try:
            os.remove(src)
            print(f"Removed legacy {src} file")
        except Exception as e:
            print(f"Warning: could not remove legacy {src}: {e}")
    else:
        # Docker inode bug로 인해 폴더로 생성된 경우
        import shutil
        try:
            shutil.rmtree(src)
            print(f"Removed buggy {src} directory.")
        except:
            pass
