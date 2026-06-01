import os
import shutil
import hashlib
import zipfile
import uuid
from src.core.logger import write_log

# 실행 위치 기준 상대 경로 명시
DROPZONE_DIR = "DropZone"
STAGING_DIR = "Staging"
MIA_BUNKER_DIR = "MIA_Bunker"
LOGS_DIR = "logs"

def setup_directories():
    os.makedirs(DROPZONE_DIR, exist_ok=True)
    os.makedirs(STAGING_DIR, exist_ok=True)
    os.makedirs(MIA_BUNKER_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    write_log("SYSTEM", "N/A", "INIT", "SETUP_DIR", "SUCCESS", "시스템 디렉터리(DropZone, Staging, MIA_Bunker, logs) 준비 완료.")

def get_sha256_hash(filepath):
    """
    대용량 파일을 고려한 청크 기반 SHA-256 추출.
    with open을 통한 파일 핸들 누수 방지.
    """
    sha256 = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096 * 1024), b""): # 4MB chunks
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        print(f"[ERROR] 해시 추출 실패 ({filepath}): {e}")
        return None

def compress_to_zip(file_path):
    """
    원본 파일을 임시 zip으로 압축한 뒤, 
    해당 ZIP 아티팩트의 해시(SHA-256)를 추출하여 File_ID로 삼고
    {File_ID}.zip 으로 파일명을 변경합니다.
    """
    base_name = os.path.basename(file_path)
    temp_id = str(uuid.uuid4())
    temp_zip_filename = f"temp_{temp_id}.zip"
    temp_zip_path = os.path.join(os.path.dirname(file_path), temp_zip_filename)

    write_log("PENDING", base_name, "PREPROCESS", "COMPRESS", "TRY", f"ZIP 임시 압축 시도: {temp_zip_filename}")
    
    try:
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(file_path, base_name)
        
        # ZIP 아티팩트의 해시를 추출 (최종 File_ID)
        file_id = get_sha256_hash(temp_zip_path)
        if not file_id:
            raise Exception("ZIP 해시 추출 실패")

        final_zip_path = os.path.join(os.path.dirname(file_path), f"{file_id}.zip")
        os.rename(temp_zip_path, final_zip_path)

        zip_size = os.path.getsize(final_zip_path)
        write_log(file_id, base_name, "PREPROCESS", "COMPRESS", "SUCCESS", f"ZIP 압축 완료 및 해시 획득. 용량: {zip_size} Bytes")
        return final_zip_path, file_id

    except Exception as e:
        write_log("ERROR", base_name, "PREPROCESS", "COMPRESS", "FAIL", f"압축 에러 발생: {str(e)}")
        if os.path.exists(temp_zip_path):
            try: os.remove(temp_zip_path)
            except: pass
        return None, None

def safe_cleanup(orig, zip_p):
    """
    무결성 검증 100% 완료 시 호출되는 안전한 삭제 (Best-effort).
    """
    try:
        if orig and os.path.exists(orig):
            os.remove(orig)
    except Exception as e:
        print(f"[WARN] 로컬 원본 삭제 실패: {e}")

    try:
        if zip_p and os.path.exists(zip_p):
            os.remove(zip_p)
    except Exception as e:
        print(f"[WARN] 로컬 ZIP 삭제 실패: {e}")
