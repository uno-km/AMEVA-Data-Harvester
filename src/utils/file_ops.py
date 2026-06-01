import os
import zipfile
from src.core.logger import write_log

DROPZONE_DIR = "DropZone"
MIA_BUNKER_DIR = "MIA_Bunker"

def setup_directories():
    """
    실행 위치에 DropZone, MIA_Bunker 폴더를 생성하고 로그 파일을 초기화합니다.
    """
    os.makedirs(DROPZONE_DIR, exist_ok=True)
    os.makedirs(MIA_BUNKER_DIR, exist_ok=True)
    
    # Initialize logger
    from src.core.logger import LOG_FILE
    if not os.path.exists(LOG_FILE):
        write_log("SYSTEM_INIT", "N/A", "INIT", "SETUP_DIR", "SUCCESS", "시스템 기본 디렉터리 생성 및 로깅 시스템 준비 완료.")


def compress_to_zip(file_path, log_id):
    """
    원본 파일을 zip 형식으로 압축하고 로컬 용량을 기록합니다.
    성공 시 zip 파일 경로를 반환합니다.
    """
    base_name = os.path.basename(file_path)
    zip_filename = f"{os.path.splitext(base_name)[0]}_{log_id}.zip"
    zip_path = os.path.join(os.path.dirname(file_path), zip_filename)

    write_log(log_id, base_name, "PREPROCESS", "COMPRESS", "TRY", f"ZIP 압축 시도: {zip_filename}")
    
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(file_path, base_name)
        
        zip_size = os.path.getsize(zip_path)
        write_log(log_id, base_name, "PREPROCESS", "COMPRESS", "SUCCESS", f"압축 완료. 용량: {zip_size} Bytes")
        return zip_path
    except Exception as e:
        write_log(log_id, base_name, "PREPROCESS", "COMPRESS", "FAIL", f"압축 에러 발생: {str(e)}")
        if os.path.exists(zip_path):
            try: os.remove(zip_path)
            except: pass
        return None


def cleanup_local_files(orig, zip_p):
    """
    로컬 원본 및 ZIP 파일을 완벽하게 제거합니다.
    """
    try:
        if os.path.exists(orig):
            os.remove(orig)
        if os.path.exists(zip_p):
            os.remove(zip_p)
    except Exception as e:
        print(f"[WARN] 로컬 파일 청소 실패: {e}")
