# AMEVA-Data-Harvester 프로젝트 상세 명세서

## 1. 프로젝트 개요
`AMEVA-Data-Harvester`는 Windows 및 Android(Termux) 환경과 같이 극단적으로 열악한 엣지(Edge) 환경에서도 구동 가능하도록 설계된 초경량 백그라운드 데이터 수집기(포워더)입니다. 데이터베이스(SQLite 등)를 일절 사용하지 않고, 오직 디렉터리(DropZone, MIA_Bunker) 이동만으로 파일의 상태를 관리합니다.

## 2. 핵심 아키텍처 및 기능

### 2.1 파일 기반 상태 관리
* **DropZone**: 사용자가 업로드할 파일을 위치시키는 대기소입니다. 스케줄러가 이곳을 주기적으로 스캔하여 압축 및 전송을 시작합니다.
* **MIA_Bunker**: 네트워크 통신이 모두 끊어졌거나 대기 상태일 때, 전송을 시도했던 ZIP 파일을 임시 보관하는 격리 구역입니다.

### 2.2 PAC(Primary, Alternate, Contingency) 통신 파이프라인
프로그램은 어떠한 네트워크 장애 상황에서도 뻗지 않고(Crash-free) 다음 플랜으로 넘어가도록 설계되었습니다.
* **[Primary] SSH 전송 (`src/network/transfers.py - run_ssh_transfer`)**: SCP를 통해 지정된 서버로 ZIP 파일을 전송합니다. 전송 후 원격지에 접속하여 파일 크기(Byte)를 조회해 무결성을 검증합니다.
* **[Alternate] API 전송 (`src/network/transfers.py - run_api_transfer`)**: SSH 연결 실패 시, cURL/Requests를 활용해 HTTP POST로 파일을 업로드합니다. 서버 응답값의 JSON 파일 크기를 통해 무결성을 검증합니다.
* **[Contingency] 텔레그램 전송 (`src/network/transfers.py - run_telegram_transfer`)**: 서버 API조차 다운되었을 때 텔레그램 봇 API를 통해 파일을 전송하고, 파일을 `MIA_Bunker`로 격리시킵니다.
* **텔레그램 비동기 구조대 (`src/network/rescue.py`)**: 텔레그램으로 보낸 파일에 대해 메인 서버(또는 관리자 봇)가 나중에 "수신 완료([SUCCESS] UUID..., SIZE...)" 답장을 보내면, 이를 캐치하여 `MIA_Bunker`에 남은 찌꺼기 파일을 최종 삭제합니다.

### 2.3 로깅 및 유틸리티
* **`src/core/logger.py`**: 모든 행동 단계를 상세히 분리하여 `harvester_logs.csv`에 시간, UUID, 수행 단계, 성공 여부를 기록합니다.
* **`src/utils/file_ops.py`**: 모든 원본 파일을 고유 UUID가 부여된 `.zip`으로 압축하여 파일 손상 및 용량 낭비를 방지합니다.

---

## 3. 전체 소스 코드 통합

아래는 프로젝트의 전체 소스 코드입니다.

### 📄 `run.py`
```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AMEVA-Data-Harvester v2.1 (초경량 엣지 포워더)
Windows 및 Android (Termux) 환경 최적화 에이전트.
- DB 미사용, 파일 시스템 기반 상태 관리.
- 전 구간 ZIP 압축 및 UUID/용량 대조 무결성 검증.
- 3단계 PAC (Primary SSH -> Alternate API -> Contingency Telegram) 통신 파이프라인.
"""

from src.utils.file_ops import setup_directories
from src.core.config import setup_config
from src.pipeline.scheduler import main_loop

def main():
    """
    하베스터 메인 진입점.
    """
    setup_directories()
    config = setup_config()
    main_loop(config)

if __name__ == "__main__":
    main()

```

### 📄 `requirements.txt`
```text
requests==2.31.0

```

### 📄 `src/core/config.py`
```python
import os
import json

CONFIG_FILE = "config.json"

# 파일 형식별 확장자 맵핑
FILE_TYPE_EXTENSIONS = {
    "image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"],
    "video": [".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv"],
    "audio": [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"],
    "text": [".txt", ".csv", ".json", ".xml", ".log", ".md"]
}

def setup_config(dropzone_dir="DropZone"):
    """
    config.json 관리 및 사용자 설정 인터페이스.
    Enter 입력 시 이전 값을 유지(Fallback)합니다.
    """
    default_config = {
        "file_type": "image",
        "target_dir": os.path.abspath(dropzone_dir),
        "interval": 60,
        "ssh_info": "user@127.0.0.1",
        "ssh_remote_dir": "/tmp/harvester_upload",
        "api_url": "http://localhost:8000/api/upload",
        "tg_bot_token": "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ",
        "tg_chat_id": "12345678"
    }

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            print(f"[WARN] config.json 읽기 실패, 기본값으로 초기화합니다. 에러: {e}")
            config = default_config
    else:
        config = default_config

    print("\n" + "="*65)
    print(" AMEVA-Data-Harvester v2.1 CLI CONFIGURATION")
    print(" - 값 입력 없이 [Enter]를 치면 기존/기본 설정을 유지합니다.")
    print("="*65)

    choices = ["image", "video", "audio", "text"]
    while True:
        val = input(f"1. 수집 파일 형식 {choices} (이전: {config.get('file_type')}) : ").strip().lower()
        if not val:
            break
        if val in choices:
            config["file_type"] = val
            break
        print(f"[오류] 형식이 유효하지 않습니다. 다음 중 선택해 주세요: {choices}")

    val = input(f"2. 수집 대상 디렉터리 경로 (이전: {config.get('target_dir')}) : ").strip()
    if val:
        config["target_dir"] = os.path.abspath(val)

    while True:
        val = input(f"3. 배치 주기 (분 단위 숫자) (이전: {config.get('interval')}) : ").strip()
        if not val:
            break
        if val.isdigit() and int(val) > 0:
            config["interval"] = int(val)
            break
        print("[오류] 0보다 큰 정수를 입력해 주세요.")

    val = input(f"4. SSH 접속 정보 (유저명@IP) (이전: {config.get('ssh_info')}) : ").strip()
    if val:
        config["ssh_info"] = val

    val = input(f"   SSH 원격 업로드 절대 경로 (이전: {config.get('ssh_remote_dir')}) : ").strip()
    if val:
        config["ssh_remote_dir"] = val

    val = input(f"5. cURL(API) URL 주소 (이전: {config.get('api_url')}) : ").strip()
    if val:
        config["api_url"] = val

    val = input(f"6. Telegram Bot Token (이전: {config.get('tg_bot_token')}) : ").strip()
    if val:
        config["tg_bot_token"] = val

    val = input(f"   Telegram Chat ID (이전: {config.get('tg_chat_id')}) : ").strip()
    if val:
        config["tg_chat_id"] = val

    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        print("\n[+] 설정 완료 및 config.json 덮어쓰기 성공.")
    except Exception as e:
        print(f"[-] config.json 저장 실패: {e}")

    print("-" * 40)
    for k, v in config.items():
        print(f"  {k}: {v}")
    print("-" * 40 + "\n")

    return config

```

### 📄 `src/core/logger.py`
```python
import os
import csv
from datetime import datetime

LOG_FILE = "harvester_logs.csv"

def write_log(log_id, filename, step, action_type, status, message):
    """
    harvester_logs.csv 파일에 상세 동작 로그를 기록합니다.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = [timestamp, log_id, filename, step, action_type, status, message]
    
    try:
        file_exists = os.path.isfile(LOG_FILE)
        with open(LOG_FILE, mode="a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "log_id(uuid)", "filename", "step", "action_type", "status", "message"])
            writer.writerow(row)
        print(f"[{timestamp}] [{status}] {step}-{action_type} | File: {filename} | Msg: {message}")
    except Exception as e:
        print(f"[CRITICAL LOGGING ERROR] CSV 쓰기 실패: {e}")

```

### 📄 `src/utils/file_ops.py`
```python
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

```

### 📄 `src/network/transfers.py`
```python
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

```

### 📄 `src/network/rescue.py`
```python
import os
import re
import requests
from src.core.logger import write_log
from src.utils.file_ops import MIA_BUNKER_DIR

UPDATE_ID_FILE = ".tg_last_update_id"

def parse_telegram_reply(text):
    """
    서버의 답장 형식 파싱: [SUCCESS] UUID:<uuid>, SIZE:<size>
    """
    pattern = r"\[SUCCESS\]\s+UUID\s*:\s*([a-fA-F0-9\-]{36})\s*,\s*SIZE\s*:\s*(\d+)"
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip().lower(), int(match.group(2).strip())
    return None, None


def get_last_update_id():
    if os.path.exists(UPDATE_ID_FILE):
        try:
            with open(UPDATE_ID_FILE, "r") as f:
                return int(f.read().strip())
        except:
            pass
    return 0


def save_last_update_id(uid):
    try:
        with open(UPDATE_ID_FILE, "w") as f:
            f.write(str(uid))
    except:
        pass


def check_telegram_replies(config):
    """
    getUpdates API를 호출하여 수신 측의 [SUCCESS] 메시지를 체크합니다.
    UUID와 SIZE가 매칭되면 MIA_Bunker에서 zip 파일을 삭제합니다.
    """
    token = config.get("tg_bot_token")
    if not token or ":" not in token:
        return

    base_url = f"https://api.telegram.org/bot{token}"
    last_id = get_last_update_id()

    params = {"timeout": 3}
    if last_id > 0:
        params["offset"] = last_id + 1

    try:
        r = requests.get(f"{base_url}/getUpdates", params=params, timeout=5)
        if r.status_code != 200:
            return
            
        updates = r.json().get("result", [])
        for update in updates:
            update_id = update.get("update_id")
            if update_id:
                save_last_update_id(update_id)

            message = update.get("message") or update.get("channel_post")
            if not message:
                continue

            from_user = message.get("from", {})
            if from_user.get("is_bot", False):
                continue

            text = message.get("text", "")
            if not text:
                continue

            ruuid, rsize = parse_telegram_reply(text)
            if ruuid and rsize:
                if os.path.exists(MIA_BUNKER_DIR):
                    for fn in os.listdir(MIA_BUNKER_DIR):
                        if fn.endswith(".zip") and ruuid in fn:
                            file_path = os.path.join(MIA_BUNKER_DIR, fn)
                            local_size = os.path.getsize(file_path)
                            
                            if local_size == rsize:
                                write_log(ruuid, fn, "ASYNC_RESCUE", "VALIDATION_OK", "SUCCESS", f"텔레그램 비동기 구조 성공. 벙커 파일 삭제.")
                                try: os.remove(file_path)
                                except Exception as e:
                                    print(f"[-] 벙커 파일 삭제 실패 ({fn}): {e}")
                            else:
                                write_log(ruuid, fn, "ASYNC_RESCUE", "VALIDATION_FAIL", "FAIL", f"용량 대조 실패. 로컬: {local_size}, 텔레그램 수신: {rsize}")
    except Exception as e:
        print(f"[RESCUE WARNING] 텔레그램 구조대 체크 예외 발생: {e}")

```

### 📄 `src/pipeline/scheduler.py`
```python
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

```

