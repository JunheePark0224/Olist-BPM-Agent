# theme.py
"""
PPT 디자인 시스템 - 모든 색상/폰트/여백 값을 이 파일에서만 관리한다.
흑백/미니멀 스타일: 흰 배경, 검정 텍스트, 회색 보조 텍스트.
색상 강조는 하이라이트(연한 배경색) 정도로만 최소한으로 사용한다.
"""

from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

# =========================
# 색상 (흑백 기반)
# =========================
BG_WHITE = RGBColor(0xFF, 0xFF, 0xFF)       # 배경
TEXT_BLACK = RGBColor(0x1A, 0x1A, 0x1A)      # 본문/헤드라인
TEXT_GRAY = RGBColor(0x80, 0x80, 0x80)       # 카테고리 라벨, 캡션
LINE_BLACK = RGBColor(0x1A, 0x1A, 0x1A)      # 구분선

HIGHLIGHT_BG = RGBColor(0xD6, 0xE8, 0xF5)    # 텍스트 하이라이트 배경 (연한 파란색)
TABLE_HEADER_BG = RGBColor(0xF2, 0xF2, 0xF2) # 표 헤더 배경 (연한 회색)
TABLE_BORDER = RGBColor(0xCC, 0xCC, 0xCC)    # 표 테두리

# =========================
# 폰트
# =========================
FONT_TITLE = "맑은 고딕"
FONT_BODY = "맑은 고딕"

SIZE_MAIN_TITLE = Pt(36)
SIZE_SLIDE_TITLE = Pt(28)
SIZE_CATEGORY_LABEL = Pt(13)
SIZE_BIG_NUMBER = Pt(48)
SIZE_BODY = Pt(14)
SIZE_TABLE_HEADER = Pt(13)
SIZE_TABLE_BODY = Pt(12)
SIZE_CAPTION = Pt(10)

# =========================
# 레이아웃 (Inches, 슬라이드 13.33 x 7.5)
# =========================
SLIDE_WIDTH = Inches(13.33)
SLIDE_HEIGHT = Inches(7.5)
MARGIN = Inches(0.6)

LABEL_TOP = Inches(0.4)
TITLE_TOP = Inches(0.7)
LINE_TOP = Inches(1.5)
CONTENT_TOP = Inches(1.8)