# config.py
"""
Olist AI Agent 프로젝트의 설정 파일
- 프로젝트 기본 경로 및 설정값 정의
- 유틸리티 함수들 (로그, 디렉토리 생성)
- Anthropic 클라이언트 설정
"""

from __future__ import annotations
import os, platform
from pathlib import Path

# =========================
# 프로젝트 기본 경로 설정
# =========================
BASE_DIR = Path(__file__).parent.parent.resolve()  # agent/
DATA_DIR = str(BASE_DIR.parent / "data")             # Olist_AI_Project/data
CONFIG_DIR = str(BASE_DIR / "config")
OUTPUT_DIR = str(BASE_DIR / "outputs")
TEMPLATE_DIR = str(BASE_DIR / "templates")

CHAT_MODEL = "claude-sonnet-5"  # 스키마 해석 및 분석용 LLM

# =========================
# 디버그 및 로깅 설정
# =========================
DEBUG = True
def log(*args):
    """디버그 모드일 때 로그 출력"""
    if DEBUG: print("[AGENT]", *args)

# =========================
# 유틸리티 함수들
# =========================
def ensure_dir(path: str) -> str:
    """디렉토리가 존재하지 않으면 생성하고 절대 경로 반환"""
    p = Path(path).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return str(p)

def get_anthropic_client():
    """Anthropic 클라이언트 인스턴스 생성"""
    from anthropic import AsyncAnthropic
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY가 없습니다. 터미널에서 설정하세요. "
            "예: PowerShell) setx ANTHROPIC_API_KEY 'sk-ant-...'"
        )
    return AsyncAnthropic(api_key=key)

# =========================
# Windows 이벤트 루프 설정
# =========================
import asyncio
if platform.system() == "Windows":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass