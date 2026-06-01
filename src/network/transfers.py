import os
import socket
import subprocess
import requests
import shlex
import shutil
from src.core.logger import write_log
from src.utils.file_ops import MIA_BUNKER_DIR

def ssh_handshake(ssh_info):
    try:
        host = ssh_info.split("@")[-1]
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect((host, 22))
        s.close()
        
        cmd = ["ssh", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes", ssh_info, "exit"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        return res.returncode == 0
    except Exception:
        return False


def run_ssh_transfer(zip_path, file_id, config):
    """
    1단계 (SSH): 
    - 원격지에 mkdir -p 로 경로를 사전에 안전 보장.
    - shlex 이스케이핑 경로로 SCP 전송 후 sha256sum 무결성 검증.
    """
    filename = os.path.basename(zip_path)
    ssh_info = config["ssh_info"]
    remote_dir = config["ssh_remote_dir"]
    remote_file_path = f"{remote_dir}/{filename}".replace("//", "/")
    
    # 셸 인젝션 방지를 위한 경로 이스케이핑
    safe_remote_dir = shlex.quote(remote_dir)
    safe_remote_path = shlex.quote(remote_file_path)

    write_log(file_id, filename, "STAGE_1_SSH", "HANDSHAKE", "TRY", f"SSH 핑 테스트: {ssh_info}")
    if not ssh_handshake(ssh_info):
        write_log(file_id, filename, "STAGE_1_SSH", "HANDSHAKE", "FAIL", "SSH 핸드쉐이크 실패.")
        return False
    
    write_log(file_id, filename, "STAGE_1_SSH", "MKDIR", "TRY", "원격 디렉터리 보장 시도(mkdir -p)")
    mkdir_cmd = ["ssh", "-o", "ConnectTimeout=5", ssh_info, f"mkdir -p {safe_remote_dir}"]
    try:
        res_mkdir = subprocess.run(mkdir_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if res_mkdir.returncode != 0:
            write_log(file_id, filename, "STAGE_1_SSH", "MKDIR", "FAIL", f"원격 디렉터리 생성 실패: {res_mkdir.stderr.strip()}")
            return False
    except Exception as e:
        write_log(file_id, filename, "STAGE_1_SSH", "MKDIR", "FAIL", f"원격 디렉터리 생성 예외: {str(e)}")
        return False

    write_log(file_id, filename, "STAGE_1_SSH", "TRANSFER", "TRY", "SCP 업로드 시작.")
    scp_cmd = ["scp", "-o", "ConnectTimeout=5", zip_path, f"{ssh_info}:{remote_file_path}"]
    try:
        res = subprocess.run(scp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        if res.returncode != 0:
            write_log(file_id, filename, "STAGE_1_SSH", "TRANSFER", "FAIL", f"SCP 실패: {res.stderr.strip()}")
            return False
        
        write_log(file_id, filename, "STAGE_1_SSH", "TRANSFER", "SUCCESS", "SCP 완료. 원격 sha256sum 무결성 검사 시도.")
        
        # 원격 서버(리눅스 기준) 해시 검증
        stat_cmd = ["ssh", "-o", "ConnectTimeout=3", ssh_info, f"sha256sum {safe_remote_path}"]
        res_stat = subprocess.run(stat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        
        if res_stat.returncode == 0:
            remote_hash = res_stat.stdout.strip().split()[0]
            if remote_hash.lower() == file_id.lower():
                write_log(file_id, filename, "STAGE_1_SSH", "VALIDATION_OK", "SUCCESS", f"무결성(SHA-256) 완벽 일치.")
                return True
            else:
                write_log(file_id, filename, "STAGE_1_SSH", "VALIDATION_FAIL", "FAIL", f"해시 불일치! 로컬: {file_id}, 원격: {remote_hash}")
        else:
            write_log(file_id, filename, "STAGE_1_SSH", "VALIDATION_FAIL", "FAIL", f"원격 해시 명령어 실패: {res_stat.stderr.strip()}")
    except Exception as e:
        write_log(file_id, filename, "STAGE_1_SSH", "TRANSFER", "FAIL", f"SSH 예외: {str(e)}")
    return False


def run_api_transfer(zip_path, file_id, config):
    """
    2단계 (API): /health 핸드쉐이크 후 /upload 로 POST 전송.
    응답 JSON의 {"status": 200, "hash": "..."} 를 ZIP 아티팩트 해시와 완벽 교차 검증.
    """
    filename = os.path.basename(zip_path)
    health_url = config["api_health_url"]
    upload_url = config["api_upload_url"]

    write_log(file_id, filename, "STAGE_2_API", "HANDSHAKE", "TRY", f"API GET 핸드쉐이크: {health_url}")
    try:
        r_get = requests.get(health_url, timeout=3)
        if r_get.status_code != 200:
            raise Exception(f"HTTP {r_get.status_code}")
        write_log(file_id, filename, "STAGE_2_API", "HANDSHAKE", "SUCCESS", "API 핸드쉐이크 완료.")
    except Exception as e:
        write_log(file_id, filename, "STAGE_2_API", "HANDSHAKE", "FAIL", f"API 헬스체크 실패: {e}")
        return False

    write_log(file_id, filename, "STAGE_2_API", "TRANSFER", "TRY", "API POST 업로드 시작.")
    try:
        with open(zip_path, "rb") as f:
            files = {"file": (filename, f, "application/zip")}
            data = {"hash": file_id}
            
            r_post = requests.post(upload_url, files=files, data=data, timeout=10)
            
        if r_post.status_code == 200:
            try:
                res_json = r_post.json()
                server_status = res_json.get("status")
                server_hash = res_json.get("hash", "").lower()
                
                if server_status == 200 and server_hash == file_id.lower():
                    write_log(file_id, filename, "STAGE_2_API", "VALIDATION_OK", "SUCCESS", f"API 무결성(SHA-256) 검증 통과.")
                    return True
                else:
                    write_log(file_id, filename, "STAGE_2_API", "VALIDATION_FAIL", "FAIL", f"응답 해시 불일치. 서버: {server_hash}")
            except Exception as e:
                write_log(file_id, filename, "STAGE_2_API", "VALIDATION_FAIL", "FAIL", f"JSON 파싱 에러: {e}")
        else:
            write_log(file_id, filename, "STAGE_2_API", "TRANSFER", "FAIL", f"API 업로드 실패 (HTTP {r_post.status_code})")
    except Exception as e:
        write_log(file_id, filename, "STAGE_2_API", "TRANSFER", "FAIL", f"API 전송 예외: {e}")
    return False


def run_telegram_transfer(zip_path, file_id, config):
    """
    3단계 (Telegram): 캡션에 일관되게 ZIP 아티팩트 해시값(File_ID)과 SIZE 기입하여 전송.
    """
    filename = os.path.basename(zip_path)
    token = config["tg_bot_token"]
    chat_id = config["allowed_chat_id"]
    local_size = os.path.getsize(zip_path)
    base_url = f"https://api.telegram.org/bot{token}"

    write_log(file_id, filename, "STAGE_3_TELEGRAM", "HANDSHAKE", "TRY", "Telegram 상태 조회.")
    try:
        r_me = requests.get(f"{base_url}/getMe", timeout=3)
        if r_me.status_code == 200:
            write_log(file_id, filename, "STAGE_3_TELEGRAM", "HANDSHAKE", "SUCCESS", "봇 정상 동작 중.")
        else:
            write_log(file_id, filename, "STAGE_3_TELEGRAM", "HANDSHAKE", "FAIL", f"getMe 실패 (HTTP {r_me.status_code})")
            return False
    except Exception as e:
        write_log(file_id, filename, "STAGE_3_TELEGRAM", "HANDSHAKE", "FAIL", f"텔레그램 통신 장애: {e}")
        return False

    write_log(file_id, filename, "STAGE_3_TELEGRAM", "TRANSFER", "TRY", "Telegram ZIP 문서 전송 중.")
    try:
        # 단일 논리 ID(sha256) 체계 적용
        caption = f"ID: {file_id}, SIZE: {local_size}"
        
        with open(zip_path, "rb") as f:
            doc_files = {"document": (filename, f)}
            doc_data = {"chat_id": chat_id, "caption": caption}
            r_doc = requests.post(f"{base_url}/sendDocument", files=doc_files, data=doc_data, timeout=15)
            
        if r_doc.status_code == 200:
            write_log(file_id, filename, "STAGE_3_TELEGRAM", "TRANSFER", "SUCCESS", "Telegram 전송 성공.")
            return True
        else:
            write_log(file_id, filename, "STAGE_3_TELEGRAM", "TRANSFER", "FAIL", f"Telegram 전송 실패 (HTTP {r_doc.status_code})")
    except Exception as e:
        write_log(file_id, filename, "STAGE_3_TELEGRAM", "TRANSFER", "FAIL", f"Telegram 전송 에러: {e}")
    return False
