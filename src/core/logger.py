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
