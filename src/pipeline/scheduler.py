import os
import time
import uuid
from src.core.config import FILE_TYPE_EXTENSIONS
from src.core.logger import write_log
from src.utils.file_ops import compress_to_zip, cleanup_local_files, DROPZONE_DIR
from src.network.transfers import run_ssh_transfer, run_api_transfer, run_telegram_transfer
from src.network.rescue import check_telegram_replies

def transmit_payload(original_file_path, config):
    """
    PAC 통신 메인 트랙.
    1. 압축 실행
    2. Primary (SSH/SCP) -> 3. Alternate (API) -> 4. Contingency (Telegram)
    """
    log_id = str(uuid.uuid4())
    filename = os.path.basename(original_file_path)

    zip_path = compress_to_zip(original_file_path, log_id)
    if not zip_path:
        write_log(log_id, filename, "PREPROCESS", "COMPRESS_FAIL", "FAIL", "압축 실패로 파일 전송을 건너뜁니다.")
        return

    # 1. SSH
    try:
        if run_ssh_transfer(zip_path, config, log_id):
            cleanup_local_files(original_file_path, zip_path)
            return
    except Exception as e:
        write_log(log_id, filename, "STAGE_1_SSH", "CRITICAL_ERR", "FAIL", f"SSH 스테이지 진행 실패 예외: {e}")

    # 2. API
    try:
        if run_api_transfer(zip_path, config, log_id):
            cleanup_local_files(original_file_path, zip_path)
            return
    except Exception as e:
        write_log(log_id, filename, "STAGE_2_API", "CRITICAL_ERR", "FAIL", f"API 스테이지 진행 실패 예외: {e}")

    # 3. Telegram
    try:
        if run_telegram_transfer(zip_path, config, log_id):
            if os.path.exists(original_file_path):
                try: os.remove(original_file_path)
                except: pass
            return
    except Exception as e:
        write_log(log_id, filename, "STAGE_3_TELEGRAM", "CRITICAL_ERR", "FAIL", f"텔레그램 스테이지 진행 실패 예외: {e}")

    write_log(log_id, filename, "PAC_PIPELINE", "PAC_ALL_FAIL", "FAIL", "모든 PAC 전송 통로가 먹통입니다. DropZone에 대기합니다.")
    if os.path.exists(zip_path):
        try: os.remove(zip_path)
        except: pass


def scan_and_process_dropzone(config):
    """
    설정된 target_dir를 스캔하여 파일형식 확장자와 부합하면 전송 파이프라인을 작동합니다.
    """
    target_dir = config.get("target_dir", DROPZONE_DIR)
    file_type = config.get("file_type", "image")

    if not os.path.exists(target_dir):
        print(f"[WARN] 스캔 디렉터리가 부재합니다: {target_dir}")
        return

    allowed_exts = FILE_TYPE_EXTENSIONS.get(file_type, [])
    
    try:
        files = os.listdir(target_dir)
    except Exception as e:
        print(f"[ERROR] 디렉터리 스캔 오류 ({target_dir}): {e}")
        return

    for filename in files:
        file_path = os.path.join(target_dir, filename)
        if os.path.isdir(file_path) or filename.endswith(".zip"):
            continue

        _, ext = os.path.splitext(filename)
        if ext.lower() in allowed_exts:
            print(f"[SCAN] 발견된 수집 대상 파일: {filename}")
            try:
                transmit_payload(file_path, config)
            except Exception as e:
                print(f"[PIPELINE ERROR] 파일 전송 중 심각한 예외: {e}")


def main_loop(config):
    """
    무한 폴링 스케줄러. 
    1) 텔레그램 비동기 구조
    2) DropZone 스캔
    3) 지정된 간격 대기
    """
    interval_seconds = config.get("interval", 60) * 60
    print(f"\n[*] AMEVA-Data-Harvester 가동 시작 (배치 주기: {config.get('interval')}분)")
    
    while True:
        try:
            print("[+] 텔레그램 조난 확인(getUpdates)...")
            check_telegram_replies(config)
            
            print("[+] DropZone 디렉터리 스캔 중...")
            scan_and_process_dropzone(config)
            
        except KeyboardInterrupt:
            print("\n[-] 하베스터가 사용자에 의해 중단되었습니다.")
            break
        except Exception as e:
            print(f"[CRITICAL LOOP EXCEPTION] {e}. 다음 주기로 대기합니다.")
            
        print(f"[*] 스케줄러 대기 중 ({config.get('interval')}분)...")
        try:
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\n[-] 하베스터가 사용자에 의해 중단되었습니다.")
            break
