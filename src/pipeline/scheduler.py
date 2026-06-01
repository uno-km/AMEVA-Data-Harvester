import os
import time
import shutil
from src.core.config import FILE_TYPE_EXTENSIONS
from src.core.logger import write_log
from src.utils.file_ops import compress_to_zip, safe_cleanup, DROPZONE_DIR, STAGING_DIR, MIA_BUNKER_DIR
from src.network.transfers import run_ssh_transfer, run_api_transfer, run_telegram_transfer
from src.network.rescue import check_telegram_replies

def transmit_payload(original_file_path, config):
    """
    PAC 통신 메인 트랙.
    original_file_path는 /Staging 구역에 위치해 있습니다.
    """
    filename = os.path.basename(original_file_path)

    zip_path, file_id = compress_to_zip(original_file_path)
    if not zip_path or not file_id:
        write_log("PENDING", filename, "PREPROCESS", "COMPRESS_FAIL", "FAIL", "압축 또는 해시 추출 실패로 전송을 건너뜁니다.")
        return

    # 1. SSH (Primary)
    try:
        if run_ssh_transfer(zip_path, file_id, config):
            safe_cleanup(original_file_path, zip_path)
            return
    except Exception as e:
        write_log(file_id, filename, "STAGE_1_SSH", "CRITICAL_ERR", "FAIL", f"SSH 스테이지 진행 실패 예외: {e}")

    # 2. API (Alternate)
    try:
        if run_api_transfer(zip_path, file_id, config):
            safe_cleanup(original_file_path, zip_path)
            return
    except Exception as e:
        write_log(file_id, filename, "STAGE_2_API", "CRITICAL_ERR", "FAIL", f"API 스테이지 진행 실패 예외: {e}")

    # 3. Telegram (Contingency)
    try:
        if run_telegram_transfer(zip_path, file_id, config):
            safe_cleanup(original_file_path, None) # zip_path는 telegram 전송에서 MIA_Bunker로 이동됨
            return
    except Exception as e:
        write_log(file_id, filename, "STAGE_3_TELEGRAM", "CRITICAL_ERR", "FAIL", f"텔레그램 스테이지 진행 실패 예외: {e}")

    # PAC 전체 실패 시 MIA_Bunker로 강제 대피 (누수 방지)
    write_log(file_id, filename, "PAC_PIPELINE", "PAC_ALL_FAIL", "FAIL", "모든 PAC 전송 통로 먹통. MIA_Bunker 강제 대피.")
    
    bunker_path = os.path.join(MIA_BUNKER_DIR, os.path.basename(zip_path))
    if os.path.exists(bunker_path):
        try: os.remove(bunker_path)
        except: pass
    try:
        shutil.move(zip_path, bunker_path)
    except Exception as e:
        write_log(file_id, filename, "PAC_PIPELINE", "BUNKER_MOVE_FAIL", "FAIL", f"MIA_Bunker 격리 실패: {e}")
        
    # 원본 파일은 이제 불필요하므로 삭제 (ZIP이 벙커에 보관됨)
    safe_cleanup(original_file_path, None)


def get_files_snapshot(target_dir, allowed_exts):
    """
    해당 디렉터리의 허용된 파일들의 크기와 mtime 스냅샷을 딕셔너리로 반환합니다.
    """
    snapshot = {}
    try:
        files = os.listdir(target_dir)
        for filename in files:
            path = os.path.join(target_dir, filename)
            if os.path.isdir(path) or filename.endswith(".zip"):
                continue

            _, ext = os.path.splitext(filename)
            if ext.lower() in allowed_exts:
                try:
                    size = os.path.getsize(path)
                    mtime = os.path.getmtime(path)
                    snapshot[filename] = {"size": size, "mtime": mtime}
                except:
                    continue
    except Exception as e:
        print(f"[ERROR] 디렉터리 스냅샷 오류: {e}")
    return snapshot


def scan_and_process_dropzone(config):
    """
    O(1) Batch Polling
    1. DropZone 스냅샷(1차)
    2. 1번만 Sleep 대기
    3. DropZone 스냅샷(2차)
    4. 1차와 2차가 동일한 '안정화' 파일 일괄 수집
    """
    target_dir = config.get("target_dir", DROPZONE_DIR)
    file_type = config.get("file_type", "image")
    wait_sec = config.get("stability_window_sec", 5)

    if not os.path.exists(target_dir):
        return

    allowed_exts = FILE_TYPE_EXTENSIONS.get(file_type, [])
    
    snapshot_1 = get_files_snapshot(target_dir, allowed_exts)
    if not snapshot_1:
        return
        
    time.sleep(wait_sec)
    
    snapshot_2 = get_files_snapshot(target_dir, allowed_exts)
    
    stable_files = []
    for filename, stats1 in snapshot_1.items():
        if filename in snapshot_2:
            stats2 = snapshot_2[filename]
            if stats1["size"] == stats2["size"] and stats1["mtime"] == stats2["mtime"]:
                stable_files.append(filename)
            else:
                print(f"[SCAN] 불안정 상태(쓰기 작업 중) 스킵 대기: {filename}")
        
    for filename in stable_files:
        print(f"[SCAN] 안정화 통과 파일 수집: {filename}")
        
        dropzone_path = os.path.join(target_dir, filename)
        staging_path = os.path.join(STAGING_DIR, filename)
        
        try:
            shutil.move(dropzone_path, staging_path)
        except Exception as e:
            print(f"[ERROR] Staging 격리 이동 실패 ({filename}): {e}")
            continue
            
        write_log("PENDING", filename, "STAGING", "MOVE", "SUCCESS", f"Staging 격리 구역 이동 완료.")
        
        try:
            transmit_payload(staging_path, config)
        except Exception as e:
            write_log("ERROR", filename, "PIPELINE", "CRITICAL_EXCEPTION", "FAIL", f"파이프라인 예외: {e}")


def main_loop(config):
    """
    무한 폴링 스케줄러.
    """
    interval_seconds = config.get("interval", 60) * 60
    print(f"\n[*] AMEVA-Data-Harvester v3.1 가동 시작 (배치 주기: {config.get('interval')}분)")
    
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
