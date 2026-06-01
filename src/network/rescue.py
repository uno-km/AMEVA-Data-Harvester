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
