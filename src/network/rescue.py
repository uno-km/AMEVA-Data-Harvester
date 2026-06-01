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
