# AMEVA-Data-Harvester v3.1 (엔터프라이즈 무결성 에디션) 프로젝트 명세서

## 1. 프로젝트 개요
`AMEVA-Data-Harvester`는 Windows 및 Android(Termux) 환경과 같이 극단적으로 열악한 엣지(Edge) 환경에서도 구동 가능하도록 설계된 초경량 백그라운드 데이터 수집기(포워더)입니다. 데이터베이스(SQLite 등)를 일절 사용하지 않고, 디렉터리 기반으로 단순하고 명확하게 관리합니다.

## 2. v3.1 핵심 업그레이드 내역 (무결성 검증 정합성을 강화)

v3.1에서 개선된 핵심 아키텍처는 다음과 같습니다.

### 2.1 2-Phase Batch Polling (O(1) Sleep 최적화)
* 수집 폴더(`/DropZone`)에 파일이 수십 개 몰려와도 파일 개수만큼 병목 대기하지 않습니다.
* 디렉터리 전체의 (size, mtime) 스냅샷을 1차로 뜨고, 루프 밖에서 단 한 번만 대기(`time.sleep`)한 후, 2차 스냅샷과 비교하여 변동이 없는 안정화 파일들을 한 번에 일괄 수집합니다.

### 2.2 ZIP 아티팩트 해시 멱등성 (Idempotency)
* 정합성 충돌을 방지하기 위해, 원본 파일의 해시가 아닌 실제 전송되는 **ZIP 파일의 완성본 해시(SHA-256)**를 고유 식별자인 `File_ID`로 사용합니다.
* 파일 압축이 완료되면 `{File_ID}.zip`으로 원자적 이름 변경이 수행됩니다.

### 2.3 인프라 전송 오류 원천 차단 및 원자적 대피
* **[Primary] SSH 전송**: 원격 디렉터리가 없을 경우를 대비해 전송 직전 `mkdir -p` (Linux/Unix 계열 전제) 명령으로 폴더 생성을 보장합니다. 전송 후 로컬 해시와 원격 셸(`sha256sum`)을 대조하여 무결성 검증 정합성을 강화했습니다.
* **[Alternate] API 전송**: 서버 응답 JSON의 `{"hash": "..."}` 값을 ZIP 아티팩트 해시와 교차 검증합니다.
* **[Contingency] 텔레그램 및 MIA_Bunker 격리**: Telegram 전송이 성공하면, 로컬 원본 파일은 즉시 삭제되고 전송된 ZIP 아티팩트는 `/MIA_Bunker` 벙커로 강제 `shutil.move` 이동하여 비동기 구출 대기 상태로 보관됩니다. 만약 1단계(SSH), 2단계(API), 3단계(Telegram)를 포함한 모든 전송 수단이 완전히 실패하더라도, 파일이 `/Staging` 구역에 방치되어 누수가 생기지 않도록 ZIP 아티팩트를 `/MIA_Bunker` 벙커로 동일하게 강제 대피시킵니다.

### 2.4 Telegram 이중 인증 (Strict Rescue Validation)
* 텔레그램 구조대가 `[SUCCESS] ID:...` 메시지를 받을 때, 발송된 **채팅방(allowed_chat_id)**과 발송한 **사용자(allowed_sender_user_id)**가 `config.json`의 권한과 완벽히 일치할 때만 스푸핑(Spoofing)을 방어하고 백업 파일을 삭제합니다.
* **MIA_Bunker 독점 대상 검증**: `rescue.py` 구조대 모듈은 오직 `/MIA_Bunker` 디렉터리 내의 파일만을 스캔하여 정리하며, 그 외 `DropZone`이나 `Staging` 영역은 어떠한 경우에도 건드리지 않습니다.

### 2.5 로깅 및 파일 핸들 누수 방지
* **일자별 로깅**: 매일 `logs/harvester_YYYYMMDD.csv` 형태로 로그 파일이 로테이션됩니다.
* 모든 파일 I/O는 `with open(...)` 컨텍스트 매니저를 강제하여 핸들 누수를 막고, 삭제 처리 역시 `safe_cleanup` 함수 내에서 개별 `try-except`로 묶어 최선(Best-effort)으로 자폭 청소합니다.

---

## 3. 전체 소스 코드 통합

아래는 프로젝트의 최신 v3.1 소스 코드 전체입니다.

### 📄 `run.py`
```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AMEVA-Data-Harvester v3.1 (엔터프라이즈 무결성 에디션)
Windows 및 Android (Termux) 환경 최적화 에이전트.
- DB 미사용, 디렉터리 기반으로 단순하고 명확하게 관리.
- 전 구간 ZIP 압축 및 ZIP 아티팩트 SHA-256 해시 검증을 통해 무결성 검증 정합성을 강화.
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

FILE_TYPE_EXTENSIONS = {
    "image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"],
    "video": [".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv"],
    "audio": [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"],
    "text": [".txt", ".csv", ".json", ".xml", ".log", ".md"]
}

def setup_config():
    default_config = {
        "file_type": "image",
        "interval": 60,
        "stability_window_sec": 5,
        "ssh_info": "user@127.0.0.1",
        "ssh_remote_dir": "/tmp/harvester_upload",
        "api_health_url": "http://localhost:8000/health",
        "api_upload_url": "http://localhost:8000/api/upload",
        "tg_bot_token": "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ",
        "allowed_chat_id": "12345678",
        "allowed_sender_user_id": "12345678"
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

    # 하위 호환성 체크
    for k, v in default_config.items():
        if k not in config:
            config[k] = v

    print("\n" + "="*65)
    print(" AMEVA-Data-Harvester v3.1 CLI CONFIGURATION")
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
        print(f"[오류] 형식이 유효하지 않습니다.")

    while True:
        val = input(f"2. 배치 주기 (분 단위 숫자) (이전: {config.get('interval')}) : ").strip()
        if not val:
            break
        if val.isdigit() and int(val) > 0:
            config["interval"] = int(val)
            break
        print("[오류] 0보다 큰 정수를 입력해 주세요.")
        
    while True:
        val = input(f"3. 파일 안정화 대기 시간(초) (이전: {config.get('stability_window_sec')}) : ").strip()
        if not val:
            break
        if val.isdigit() and int(val) > 0:
            config["stability_window_sec"] = int(val)
            break
        print("[오류] 0보다 큰 정수를 입력해 주세요.")

    val = input(f"4. SSH 접속 정보 (유저명@IP) (이전: {config.get('ssh_info')}) : ").strip()
    if val: config["ssh_info"] = val

    val = input(f"   SSH 원격 절대 경로 (이전: {config.get('ssh_remote_dir')}) : ").strip()
    if val: config["ssh_remote_dir"] = val

    val = input(f"5. API Health URL (이전: {config.get('api_health_url')}) : ").strip()
    if val: config["api_health_url"] = val
    
    val = input(f"   API Upload URL (이전: {config.get('api_upload_url')}) : ").strip()
    if val: config["api_upload_url"] = val

    val = input(f"6. Telegram Bot Token (이전: {config.get('tg_bot_token')}) : ").strip()
    if val: config["tg_bot_token"] = val

    val = input(f"   Telegram 허용된 Chat ID (이전: {config.get('allowed_chat_id')}) : ").strip()
    if val: config["allowed_chat_id"] = str(val)
    
    val = input(f"   Telegram 허용된 발신자 User ID (이전: {config.get('allowed_sender_user_id')}) : ").strip()
    if val: config["allowed_sender_user_id"] = str(val)

    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        print("\n[+] 설정 완료 및 config.json 덮어쓰기 성공.")
    except Exception as e:
        print(f"[-] config.json 저장 실패: {e}")

    return config

```

### 📄 `src/core/logger.py`
```python
import os
import csv
from datetime import datetime

LOGS_DIR = "logs"

def get_log_file():
    os.makedirs(LOGS_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    return os.path.join(LOGS_DIR, f"harvester_{today}.csv")

def write_log(file_hash, filename, step, action_type, status, message):
    """
    일자별 CSV 로깅.
    헤더: timestamp, file_hash, filename, step, action_type, status, message
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = [timestamp, file_hash, filename, step, action_type, status, message]
    log_file = get_log_file()
    
    try:
        file_exists = os.path.isfile(log_file)
        with open(log_file, mode="a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "file_hash", "filename", "step", "action_type", "status", "message"])
            writer.writerow(row)
        print(f"[{timestamp}] [{status}] {step}-{action_type} | File: {filename} | Msg: {message}")
    except Exception as e:
        print(f"[CRITICAL LOGGING ERROR] CSV 쓰기 실패: {e}")

```

### 📄 `src/utils/file_ops.py`
```python
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

```

### 📄 `src/network/transfers.py`
```python
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
    서버의 답장 형식 파싱: [SUCCESS] ID:<sha256>
    """
    pattern = r"\[SUCCESS\]\s*ID:\s*([a-fA-F0-9]{64})"
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip().lower()
    return None


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
    Telegram Rescue Strict Validation.
    메시지의 Chat ID와 Sender User ID가 모두 허용된 목록과 일치할 때만 파싱을 시도합니다.
    [중요] 이 함수(rescue.py)는 오직 MIA_Bunker 디렉터리(MIA_BUNKER_DIR) 내에 보존되어 대기 중인 
    ZIP 파일들만을 대상으로 자동 검증 및 삭제 처리를 수행하며, 그 외 DropZone이나 Staging 영역은 일절 건드리지 않습니다.
    """
    token = config.get("tg_bot_token")
    if not token or ":" not in token:
        return

    allowed_chat_id = str(config.get("allowed_chat_id", ""))
    allowed_sender_id = str(config.get("allowed_sender_user_id", ""))

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

            # 1. 채팅방(공간) 검증
            chat = message.get("chat", {})
            if str(chat.get("id")) != allowed_chat_id:
                continue

            # 2. 발신자(유저/봇) 검증
            from_user = message.get("from", {})
            if str(from_user.get("id")) != allowed_sender_id:
                continue

            text = message.get("text", "")
            if not text:
                continue

            ruuid = parse_telegram_reply(text)
            if ruuid:
                if os.path.exists(MIA_BUNKER_DIR):
                    for fn in os.listdir(MIA_BUNKER_DIR):
                        if fn.endswith(".zip") and ruuid in fn:
                            file_path = os.path.join(MIA_BUNKER_DIR, fn)
                            
                            # 파일이 이미 삭제된 중복 요청의 경우 스킵
                            if not os.path.exists(file_path):
                                continue
                            
                            write_log(ruuid, fn, "ASYNC_RESCUE", "VALIDATION_OK", "SUCCESS", f"텔레그램 비동기 구조 인증 완료. 벙커 파일 완벽 삭제.")
                            try: os.remove(file_path)
                            except Exception as e:
                                print(f"[-] 벙커 파일 삭제 실패 ({fn}): {e}")
    except Exception as e:
        print(f"[RESCUE WARNING] 텔레그램 구조대 체크 예외 발생: {e}")

```

### 📄 `src/pipeline/scheduler.py`
```python
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
            # Telegram 전송 성공 시, ZIP 아티팩트를 비동기 구출 대기(MIA_Bunker 이동) 상태로 보관합니다.
            bunker_path = os.path.join(MIA_BUNKER_DIR, os.path.basename(zip_path))
            if os.path.exists(bunker_path):
                try: os.remove(bunker_path)
                except: pass
            try:
                shutil.move(zip_path, bunker_path)
                write_log(file_id, filename, "STAGE_3_TELEGRAM", "BUNKER_MOVE", "SUCCESS", "Telegram 전송 성공 후 ZIP 아티팩트 MIA_Bunker 이동 보관 완료.")
            except Exception as e:
                write_log(file_id, filename, "STAGE_3_TELEGRAM", "BUNKER_MOVE_FAIL", "FAIL", f"Telegram 전송 성공 후 MIA_Bunker 이동 실패: {e}")
            
            # 원본 파일은 즉시 안전 삭제
            safe_cleanup(original_file_path, None)
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

```

