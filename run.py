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
