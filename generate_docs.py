import os

DOC_FILENAME = "project_documentation.md"

def generate_docs():
    content = """# AMEVA-Data-Harvester 프로젝트 상세 명세서

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
    
    print(f"[+] 성공적으로 {DOC_FILENAME} 문서가 생성되었습니다.")

if __name__ == "__main__":
    generate_docs()
