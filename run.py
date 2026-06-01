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
