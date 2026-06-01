import os

DOC_FILENAME = "project_documentation.md"

def generate_docs():
    content = """# AMEVA-Data-Harvester v3.1 (엔터프라이즈 무결성 에디션) 프로젝트 명세서

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
* **[Contingency] 텔레그램 및 MIA_Bunker 격리**: 위 모든 전송 방식이 실패하더라도, 파일이 `/Staging` 구역에 방치되어 누수가 생기지 않도록 즉시 `/MIA_Bunker` 벙커로 강제 `shutil.move` 대피합니다.

### 2.4 Telegram 이중 인증 (Strict Rescue Validation)
* 텔레그램 구조대가 `[SUCCESS] ID:...` 메시지를 받을 때, 발송된 **채팅방(allowed_chat_id)**과 발송한 **사용자(allowed_sender_user_id)**가 `config.json`의 권한과 완벽히 일치할 때만 스푸핑(Spoofing)을 방어하고 백업 파일을 삭제합니다.

### 2.5 로깅 및 파일 핸들 누수 방지
* **일자별 로깅**: 매일 `logs/harvester_YYYYMMDD.csv` 형태로 로그 파일이 로테이션됩니다.
* 모든 파일 I/O는 `with open(...)` 컨텍스트 매니저를 강제하여 핸들 누수를 막고, 삭제 처리 역시 `safe_cleanup` 함수 내에서 개별 `try-except`로 묶어 최선(Best-effort)으로 자폭 청소합니다.

---

## 3. 전체 소스 코드 통합

아래는 프로젝트의 최신 v3.1 소스 코드 전체입니다.

"""
    
    files_to_include = [
        "run.py",
        "requirements.txt",
        "src/core/config.py",
        "src/core/logger.py",
        "src/utils/file_ops.py",
        "src/network/transfers.py",
        "src/network/rescue.py",
        "src/pipeline/scheduler.py"
    ]
    
    with open(DOC_FILENAME, "w", encoding="utf-8") as f:
        f.write(content)
        
        for file_path in files_to_include:
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as src:
                        code = src.read()
                    
                    ext = os.path.splitext(file_path)[1].replace(".", "")
                    if ext == "py":
                        lang = "python"
                    elif ext == "txt":
                        lang = "text"
                    else:
                        lang = ""
                    
                    f.write(f"### 📄 `{file_path}`\n")
                    f.write(f"```{lang}\n")
                    f.write(code)
                    f.write("\n```\n\n")
                except Exception as e:
                    f.write(f"> `{file_path}` 파일을 읽는 중 오류 발생: {e}\n\n")
            else:
                f.write(f"> ⚠️ `{file_path}` 파일을 찾을 수 없습니다.\n\n")
    
    print(f"[+] 성공적으로 v3.1 기준 {DOC_FILENAME} 문서가 갱신되었습니다.")

if __name__ == "__main__":
    generate_docs()
