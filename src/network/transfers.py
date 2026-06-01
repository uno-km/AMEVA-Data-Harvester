import os
import socket
import subprocess
import requests
from src.core.logger import write_log
from src.utils.file_ops import MIA_BUNKER_DIR

def ssh_handshake(ssh_info):
    """
    SSH 핑 테스트. 포트 22가 열려있는지 소켓 확인 후, SSH 접속 커넥션 체크.
    """
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


def run_ssh_transfer(zip_path, config, log_id):
    """
    1단계 (SSH): scp 전송 -> 원격 서버에서 stat 명령어로 파일 사이즈 조회 -> 로컬 용량과 대조
    """
    filename = os.path.basename(zip_path)
    ssh_info = config["ssh_info"]
    remote_dir = config["ssh_remote_dir"]
    local_size = os.path.getsize(zip_path)
    remote_file_path = f"{remote_dir}/{filename}".replace("//", "/")

    write_log(log_id, filename, "STAGE_1_SSH", "HANDSHAKE_TRY", "TRY", f"SSH 서버 핑 테스트 중 ({ssh_info})")
    if not ssh_handshake(ssh_info):
        write_log(log_id, filename, "STAGE_1_SSH", "HANDSHAKE_FAIL", "FAIL", "SSH/SCP 핸드쉐이크 실패.")
        return False
    
    write_log(log_id, filename, "STAGE_1_SSH", "HANDSHAKE_OK", "SUCCESS", "SSH 핸드쉐이크 성공. SCP 전송 준비.")

    write_log(log_id, filename, "STAGE_1_SSH", "TRANSFER", "TRY", "SCP를 통한 ZIP 파일 업로드 시작.")
    scp_cmd = ["scp", "-o", "ConnectTimeout=5", zip_path, f"{ssh_info}:{remote_file_path}"]
    try:
        res = subprocess.run(scp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        if res.returncode != 0:
            write_log(log_id, filename, "STAGE_1_SSH", "TRANSFER", "FAIL", f"SCP 전송 실패: {res.stderr.strip()}")
            return False
        
        write_log(log_id, filename, "STAGE_1_SSH", "TRANSFER", "SUCCESS", "SCP 전송 완료. 원격 서버 용량 확인 중.")
        stat_cmd = ["ssh", "-o", "ConnectTimeout=3", ssh_info, f"stat -c%s {remote_file_path}"]
        res_stat = subprocess.run(stat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        
        if res_stat.returncode != 0:
            stat_cmd = ["ssh", "-o", "ConnectTimeout=3", ssh_info, f"wc -c {remote_file_path}"]
            res_stat = subprocess.run(stat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            
        if res_stat.returncode == 0:
            try:
                remote_size = int(res_stat.stdout.strip().split()[0])
                if remote_size == local_size:
                    write_log(log_id, filename, "STAGE_1_SSH", "VALIDATION_OK", "SUCCESS", f"용량 완벽 일치 ({local_size} Bytes).")
                    return True
                else:
                    write_log(log_id, filename, "STAGE_1_SSH", "VALIDATION_FAIL", "FAIL", f"용량 불일치! 로컬: {local_size}, 원격: {remote_size}")
            except Exception as e:
                write_log(log_id, filename, "STAGE_1_SSH", "VALIDATION_FAIL", "FAIL", f"원격 용량 텍스트 파싱 실패: {e}")
        else:
            write_log(log_id, filename, "STAGE_1_SSH", "VALIDATION_FAIL", "FAIL", f"원격 크기 조회 명령어 실패: {res_stat.stderr.strip()}")
    except Exception as e:
        write_log(log_id, filename, "STAGE_1_SSH", "TRANSFER", "FAIL", f"SSH 파이프라인 에러: {str(e)}")
    return False


def run_api_transfer(zip_path, config, log_id):
    """
    2단계 (API): GET 핸드쉐이크 -> POST로 ZIP 업로드 -> 응답 JSON의 수신 size와 로컬 용량 비교
    """
    filename = os.path.basename(zip_path)
    api_url = config["api_url"]
    local_size = os.path.getsize(zip_path)

    write_log(log_id, filename, "STAGE_2_API", "HANDSHAKE_TRY", "TRY", f"API GET 핸드쉐이크 테스트 중 ({api_url})")
    try:
        r_get = requests.get(api_url, timeout=3)
        write_log(log_id, filename, "STAGE_2_API", "HANDSHAKE_OK", "SUCCESS", f"API 핸드쉐이크 완료 (HTTP {r_get.status_code})")
    except Exception as e:
        write_log(log_id, filename, "STAGE_2_API", "HANDSHAKE_FAIL", "FAIL", f"API 핸드쉐이크 실패: {e}")
        return False

    write_log(log_id, filename, "STAGE_2_API", "TRANSFER", "TRY", "API POST 업로드 시작.")
    try:
        files = {"file": (filename, open(zip_path, "rb"), "application/zip")}
        data = {"uuid": log_id}
        
        r_post = requests.post(api_url, files=files, data=data, timeout=10)
        if r_post.status_code == 200:
            try:
                res_json = r_post.json()
                server_status = res_json.get("status")
                server_size = res_json.get("size")
                
                if server_status == 200 and server_size == local_size:
                    write_log(log_id, filename, "STAGE_2_API", "VALIDATION_OK", "SUCCESS", f"API 업로드 검증 완료 ({server_size} Bytes).")
                    return True
                else:
                    write_log(log_id, filename, "STAGE_2_API", "VALIDATION_FAIL", "FAIL", f"API 응답 용량 불일치. 서버수신크기: {server_size}, status: {server_status}")
            except Exception as e:
                write_log(log_id, filename, "STAGE_2_API", "VALIDATION_FAIL", "FAIL", f"응답 JSON 파싱 에러: {e}")
        else:
            write_log(log_id, filename, "STAGE_2_API", "TRANSFER", "FAIL", f"API POST 실패 (HTTP {r_post.status_code})")
    except Exception as e:
        write_log(log_id, filename, "STAGE_2_API", "TRANSFER", "FAIL", f"API 전송 에러: {e}")
    return False


def run_telegram_transfer(zip_path, config, log_id):
    """
    3단계 (Telegram): getMe 핸드쉐이크 -> 문서 전송 (Caption에 UUID, SIZE 명시) -> MIA_Bunker 이동
    """
    filename = os.path.basename(zip_path)
    token = config["tg_bot_token"]
    chat_id = config["tg_chat_id"]
    local_size = os.path.getsize(zip_path)
    base_url = f"https://api.telegram.org/bot{token}"

    write_log(log_id, filename, "STAGE_3_TELEGRAM", "HANDSHAKE_TRY", "TRY", "Telegram getMe 상태 조회 시도.")
    try:
        r_me = requests.get(f"{base_url}/getMe", timeout=3)
        if r_me.status_code == 200:
            write_log(log_id, filename, "STAGE_3_TELEGRAM", "HANDSHAKE_OK", "SUCCESS", "텔레그램 봇 상태 확인 완료.")
        else:
            write_log(log_id, filename, "STAGE_3_TELEGRAM", "HANDSHAKE_FAIL", "FAIL", f"getMe 실패 (HTTP {r_me.status_code})")
            return False
    except Exception as e:
        write_log(log_id, filename, "STAGE_3_TELEGRAM", "HANDSHAKE_FAIL", "FAIL", f"텔레그램 통신 장애: {e}")
        return False

    write_log(log_id, filename, "STAGE_3_TELEGRAM", "TRANSFER", "TRY", "Telegram ZIP 문서 전송 중.")
    try:
        caption = f"UUID: {log_id}, SIZE: {local_size}"
        doc_files = {"document": (filename, open(zip_path, "rb"))}
        doc_data = {"chat_id": chat_id, "caption": caption}
        
        r_doc = requests.post(f"{base_url}/sendDocument", files=doc_files, data=doc_data, timeout=15)
        if r_doc.status_code == 200:
            write_log(log_id, filename, "STAGE_3_TELEGRAM", "TRANSFER", "SUCCESS", "Telegram 전송 성공. 벙커(MIA_Bunker)로 격리 이송합니다.")
            
            bunker_path = os.path.join(MIA_BUNKER_DIR, filename)
            if os.path.exists(bunker_path):
                try: os.remove(bunker_path)
                except: pass
            os.rename(zip_path, bunker_path)
            
            write_log(log_id, filename, "STAGE_3_TELEGRAM", "VALIDATION_PENDING", "SUCCESS", f"벙커 보관됨: {bunker_path}")
            return True
        else:
            write_log(log_id, filename, "STAGE_3_TELEGRAM", "TRANSFER", "FAIL", f"Telegram 전송 실패 (HTTP {r_doc.status_code})")
    except Exception as e:
        write_log(log_id, filename, "STAGE_3_TELEGRAM", "TRANSFER", "FAIL", f"Telegram 전송 에러: {e}")
    return False
