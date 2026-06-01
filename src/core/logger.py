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
