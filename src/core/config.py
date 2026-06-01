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
    print(" AMEVA-Data-Harvester v3.0 CLI CONFIGURATION")
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
