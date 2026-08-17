# ppt_generator.py
"""
⑨-2 PPT Generator 모듈
- report_data.json만 읽어서 슬라이드를 렌더링한다.
- 이전 분석 로직(bottleneck_report.json 등)의 존재를 전혀 모른다.

설계 원칙: slide["type"]별로 render_* 함수를 매칭하는 레지스트리 구조.
새 슬라이드 타입이 필요하면 render 함수 하나만 추가하면 되고,
기존 함수는 건드리지 않는다. 좌표/색상/폰트는 theme.py의 상수만
참조하며 이 파일에 직접 하드코딩하지 않는다.

11개 슬라이드 타입 구현 완료:
TitleSlide, BigNumberSlide, DataTableSlide, SummaryCardSlide,
ImageSlide, KPIDashboardSlide, ChartInsightSlide, DualImageSlide,
ExperimentSlide, RoadmapSlide, ClosingSlide
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
import theme as t

# 이미지 렌더링이 필요한 타입 (run()에서 images_dir을 추가로 전달)
IMAGE_SLIDE_TYPES = ("ImageSlide", "KPIDashboardSlide", "ChartInsightSlide", "DualImageSlide")


# =========================
# 1. 공통 헬퍼
# =========================
def add_blank_slide(prs: Presentation):
    """빈 흰 배경 슬라이드를 하나 추가하고 반환한다."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.background
    bg.fill.solid()
    bg.fill.fore_color.rgb = t.BG_WHITE
    return slide


def add_header(slide, category_label: str, title: str):
    """
    모든 콘텐츠 슬라이드가 공유하는 헤더를 그린다.
    작은 회색 카테고리 라벨 + 굵은 제목 + 얇은 구분선.

    Args:
        slide: python-pptx slide 객체
        category_label: 작은 회색 라벨 (예: "Root Cause Analysis")
        title: 굵은 제목 텍스트
    """
    label_box = slide.shapes.add_textbox(t.MARGIN, t.LABEL_TOP, Inches(10), Inches(0.3))
    label_run = label_box.text_frame.paragraphs[0].add_run()
    label_run.text = category_label
    label_run.font.size = t.SIZE_CATEGORY_LABEL
    label_run.font.color.rgb = t.TEXT_GRAY
    label_run.font.bold = True
    label_run.font.name = t.FONT_BODY

    title_box = slide.shapes.add_textbox(t.MARGIN, t.TITLE_TOP, Inches(12), Inches(0.6))
    title_run = title_box.text_frame.paragraphs[0].add_run()
    title_run.text = title
    title_run.font.size = t.SIZE_SLIDE_TITLE
    title_run.font.bold = True
    title_run.font.color.rgb = t.TEXT_BLACK
    title_run.font.name = t.FONT_TITLE

    line = slide.shapes.add_connector(1, t.MARGIN, t.LINE_TOP, t.SLIDE_WIDTH - t.MARGIN, t.LINE_TOP)
    line.line.color.rgb = t.LINE_BLACK
    line.line.width = Pt(1.25)


def set_run(paragraph, text: str, size=None, bold: bool = False, color=None, font_name: str = None):
    """paragraph에 run 하나를 추가하고 스타일을 지정하는 축약 헬퍼."""
    run = paragraph.add_run()
    run.text = text
    run.font.size = size or t.SIZE_BODY
    run.font.bold = bold
    run.font.color.rgb = color or t.TEXT_BLACK
    run.font.name = font_name or t.FONT_BODY
    return run


def _set_cell_border(cell, color_hex: str = "CCCCCC", width_pt: float = 0.75):
    """
    python-pptx는 표 셀 테두리를 고수준 API로 노출하지 않아서
    XML(a:tcPr)에 직접 라인을 추가한다. 상/하/좌/우 4개 선을
    동일한 색상/두께로 그려 심플한 그리드 라인을 만든다.

    주의: OOXML 스펙상 tcPr의 자식 요소는 border(lnL/lnR/lnT/lnB) →
    fill 순서를 지켜야 한다. 이 함수는 항상 fill을 설정하기 "전"에
    호출해야 한다 — 순서가 반대가 되면 PowerPoint/LibreOffice가
    테두리를 조용히 무시한다.
    """
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        ln = tcPr.find(qn(tag))
        if ln is None:
            ln = tcPr.makeelement(qn(tag), {})
            tcPr.append(ln)
        ln.set("w", str(int(width_pt * 12700)))  # pt -> EMU
        for child in list(ln):
            ln.remove(child)
        solidFill = ln.makeelement(qn("a:solidFill"), {})
        srgbClr = solidFill.makeelement(qn("a:srgbClr"), {"val": color_hex})
        solidFill.append(srgbClr)
        ln.append(solidFill)


def _add_table(slide, table_data: Dict[str, Any], top, width, max_rows: int = None):
    """
    headers/rows 딕셔너리를 받아 python-pptx 표로 렌더링.
    헤더는 굵게 + 연한 회색 배경, 본문은 흰 배경 + 얇은 회색 테두리.
    max_rows를 넘으면 상위 max_rows개만 표시한다 (표가 슬라이드
    밖으로 밀려나는 것을 방지).

    Args:
        slide: python-pptx slide 객체
        table_data: {"headers": [...], "rows": [[...], ...]}
        top: 표 시작 y 좌표
        width: 표 전체 너비
        max_rows: 표시할 최대 데이터 행 수 (None이면 전부 표시)
    """
    headers = table_data["headers"]
    rows_data = table_data["rows"]
    if max_rows is not None and len(rows_data) > max_rows:
        rows_data = rows_data[:max_rows]

    n_rows = len(rows_data) + 1
    n_cols = len(headers)
    row_height = Inches(0.4)
    table_height = Emu(row_height * n_rows)

    shape = slide.shapes.add_table(n_rows, n_cols, t.MARGIN, top, width, table_height)
    table = shape.table
    table.first_row = False
    table.horz_banding = False

    for col_idx, header in enumerate(headers):
        cell = table.cell(0, col_idx)
        _set_cell_border(cell)  # 테두리를 fill보다 먼저 (OOXML 순서 규칙)
        cell.fill.solid()
        cell.fill.fore_color.rgb = t.TABLE_HEADER_BG
        set_run(cell.text_frame.paragraphs[0], str(header), size=t.SIZE_TABLE_HEADER, bold=True)

    for row_idx, row_values in enumerate(rows_data, start=1):
        for col_idx, value in enumerate(row_values):
            cell = table.cell(row_idx, col_idx)
            _set_cell_border(cell)
            cell.fill.solid()
            cell.fill.fore_color.rgb = t.BG_WHITE
            set_run(cell.text_frame.paragraphs[0], str(value), size=t.SIZE_TABLE_BODY)

    return table


def _add_side_by_side_images(slide, images: List[Dict[str, Any]], images_dir: str, top, max_height):
    """
    이미지 여러 장을 가로로 나란히, 원본 비율을 유지하며 배치하는 공통 헬퍼.
    DualImageSlide와 KPIDashboardSlide가 함께 사용한다.

    Args:
        images: [{"path": "images/xxx.png", "caption": "..."}] 형태 리스트
        images_dir: 상대 path를 붙일 기준 폴더
        top: 이미지 시작 y 좌표
        max_height: 이미지 1장의 최대 높이 (비율 유지 기준)
    """
    from PIL import Image

    n = len(images)
    gap = Inches(0.3)
    total_width = t.SLIDE_WIDTH - 2 * t.MARGIN
    slot_width = Emu(int((total_width - gap * (n - 1)) / n))
    x = t.MARGIN

    for img_info in images:
        image_path = str(Path(images_dir) / img_info["path"].replace("images/", ""))
        if not Path(image_path).exists():
            placeholder = slide.shapes.add_textbox(x, top, slot_width, Inches(0.5))
            set_run(placeholder.text_frame.paragraphs[0], "[이미지 없음]", color=t.TEXT_GRAY)
            x = Emu(x + slot_width + gap)
            continue

        with Image.open(image_path) as img:
            img_w, img_h = img.size
        ratio = img_w / img_h

        if slot_width / ratio <= max_height:
            width = slot_width
            height = Emu(int(slot_width / ratio))
        else:
            height = max_height
            width = Emu(int(max_height * ratio))

        img_left = Emu(int(x + (slot_width - width) / 2))
        slide.shapes.add_picture(image_path, img_left, top, width=width, height=height)

        if img_info.get("caption"):
            cap_box = slide.shapes.add_textbox(x, Emu(top + max_height + Inches(0.1)), slot_width, Inches(0.3))
            cap_box.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
            set_run(cap_box.text_frame.paragraphs[0], img_info["caption"], size=Pt(16), color=t.TEXT_GRAY)

        x = Emu(x + slot_width + gap)


# =========================
# 2. TitleSlide
# =========================
def render_title_slide(prs: Presentation, data: Dict[str, Any]):
    """커버 슬라이드: 메인 타이틀 + 서브타이틀 + 메타 정보 + 하단 stat 카드 3개."""
    slide = add_blank_slide(prs)

    main_box = slide.shapes.add_textbox(t.MARGIN, Inches(2.0), Inches(11), Inches(1.0))
    set_run(main_box.text_frame.paragraphs[0], data["main_title"], size=t.SIZE_MAIN_TITLE, bold=True)

    sub_box = slide.shapes.add_textbox(t.MARGIN, Inches(2.9), Inches(11), Inches(1.0))
    set_run(sub_box.text_frame.paragraphs[0], data["subtitle"], size=Pt(22), color=t.TEXT_GRAY)

    meta_box = slide.shapes.add_textbox(t.MARGIN, Inches(3.9), Inches(11), Inches(0.4))
    set_run(meta_box.text_frame.paragraphs[0], data["meta"], size=Pt(13), color=t.TEXT_GRAY)

    line = slide.shapes.add_connector(1, t.MARGIN, Inches(4.5), Inches(4.5), Inches(4.5))
    line.line.color.rgb = t.LINE_BLACK
    line.line.width = Pt(1.25)

    cards = data["stat_cards"]
    card_width = Inches(3.6)
    gap = Inches(0.4)
    x = t.MARGIN
    y = Inches(5.2)
    for card in cards:
        box = slide.shapes.add_textbox(x, y, card_width, Inches(1.0))
        tf = box.text_frame
        set_run(tf.paragraphs[0], card["value"], size=Pt(24), bold=True)
        p2 = tf.add_paragraph()
        set_run(p2, card["label"], size=Pt(12), color=t.TEXT_GRAY)
        x = Emu(x + card_width + gap)

    return slide


# =========================
# 3. BigNumberSlide
# =========================
def render_big_number_slide(prs: Presentation, data: Dict[str, Any]):
    """큰 숫자 콜아웃 + context/highlight 텍스트 + 표 + footnote (예: Business Problem)."""
    slide = add_blank_slide(prs)
    add_header(slide, data.get("category_label", ""), data["title"])

    box = slide.shapes.add_textbox(t.MARGIN, t.CONTENT_TOP, Inches(4), Inches(1.2))
    set_run(box.text_frame.paragraphs[0], data["big_number"], size=t.SIZE_BIG_NUMBER, bold=True)

    ctx_box = slide.shapes.add_textbox(Inches(4.8), Inches(1.9), Inches(7.5), Inches(0.4))
    set_run(ctx_box.text_frame.paragraphs[0], data["context"], size=Pt(14), color=t.TEXT_GRAY)

    hl_box = slide.shapes.add_textbox(Inches(4.8), Inches(2.3), Inches(7.5), Inches(0.5))
    set_run(hl_box.text_frame.paragraphs[0], data["highlight"], size=Pt(18), bold=True)

    _add_table(slide, data["table"], top=Inches(3.2), width=Inches(12.13))

    if data.get("footnote"):
        fn_box = slide.shapes.add_textbox(t.MARGIN, Inches(6.9), Inches(12), Inches(0.4))
        set_run(fn_box.text_frame.paragraphs[0], data["footnote"], size=t.SIZE_CAPTION, color=t.TEXT_GRAY)

    return slide


# =========================
# 4. SummaryCardSlide
# =========================
def render_summary_card_slide(prs: Presentation, data: Dict[str, Any]):
    """
    4개 카드를 가로로 나열. 각 카드는 얇은 검정 테두리 박스 안에
    label(카드 상단 고정) / value(큰 굵은 글씨) / caption(작은 설명) 구조.
    라벨을 카드 도형의 본문 텍스트가 아니라 별도 텍스트박스로 분리해서,
    value가 여러 줄이 되어도 라벨 위치가 카드마다 항상 동일하게 고정된다.
    """
    slide = add_blank_slide(prs)
    add_header(slide, data.get("category_label", ""), data["title"])

    cards = data["cards"]
    n = len(cards)
    gap = Inches(0.3)
    total_width = t.SLIDE_WIDTH - 2 * t.MARGIN
    card_width = Emu(int((total_width - gap * (n - 1)) / n))
    card_height = Inches(3.5)
    top = t.CONTENT_TOP
    x = t.MARGIN

    for card in cards:
        box_shape = slide.shapes.add_shape(1, x, top, card_width, card_height)  # 1 = RECTANGLE
        box_shape.fill.background()
        box_shape.line.color.rgb = t.LINE_BLACK
        box_shape.line.width = Pt(1.0)
        box_shape.shadow.inherit = False

        label_box = slide.shapes.add_textbox(
            Emu(x + Inches(0.15)), Emu(top + Inches(0.25)), Emu(card_width - Inches(0.3)), Inches(0.4)
        )
        set_run(label_box.text_frame.paragraphs[0], card["label"], size=Pt(17), bold=True, color=t.TEXT_GRAY)

        body_box = slide.shapes.add_textbox(
            Emu(x + Inches(0.15)), Emu(top + Inches(1.3)), Emu(card_width - Inches(0.3)), Inches(1.8)
        )
        tf = body_box.text_frame
        tf.word_wrap = True
        set_run(tf.paragraphs[0], str(card["value"]), size=Pt(26), bold=True)
        p2 = tf.add_paragraph()
        p2.space_before = Pt(10)
        set_run(p2, card["caption"], size=Pt(12), color=t.TEXT_GRAY)

        x = Emu(x + card_width + gap)

    return slide


# =========================
# 5. DataTableSlide
# =========================
def render_data_table_slide(prs: Presentation, data: Dict[str, Any]):
    """
    제목 + (선택)부제 + 표 + (선택)key_insight (예: Business Impact, Recommended Scenarios).
    행이 많은 표(예: Business Impact의 12행)는 상위 6개만 표시해
    슬라이드 밖으로 넘치지 않게 한다.
    """
    slide = add_blank_slide(prs)
    add_header(slide, data.get("category_label", ""), data["title"])

    top = t.CONTENT_TOP
    if data.get("subtitle"):
        sub_box = slide.shapes.add_textbox(t.MARGIN, top, Inches(12), Inches(0.4))
        set_run(sub_box.text_frame.paragraphs[0], data["subtitle"], size=Pt(14), color=t.TEXT_GRAY)
        top = Emu(top + Inches(0.5))

    _add_table(slide, data["table"], top=top, width=Inches(12.13), max_rows=6)

    if data.get("key_insight"):
        ki_box = slide.shapes.add_textbox(t.MARGIN, Inches(6.9), Inches(12), Inches(0.5))
        set_run(ki_box.text_frame.paragraphs[0], data["key_insight"], size=Pt(13), bold=True)

    return slide


# =========================
# 6. ImageSlide
# =========================
def render_image_slide(prs: Presentation, data: Dict[str, Any], images_dir: str):
    """
    이미지 1장을 슬라이드 중앙에 배치 + 하단 캡션 텍스트.
    이미지가 콘텐츠 영역(가로 12.13", 세로 4.8" 이내)에 맞도록
    원본 비율을 유지하면서 크기를 제한한다.
    """
    slide = add_blank_slide(prs)
    add_header(slide, data.get("category_label", ""), data["title"])

    image_info = data["images"][0]
    image_path = str(Path(images_dir) / image_info["path"].replace("images/", ""))

    max_width = Inches(12.13)
    max_height = Inches(4.8)

    if Path(image_path).exists():
        from PIL import Image
        with Image.open(image_path) as img:
            img_w, img_h = img.size
        ratio = img_w / img_h

        if max_width / ratio <= max_height:
            width = max_width
            height = Emu(int(max_width / ratio))
        else:
            height = max_height
            width = Emu(int(max_height * ratio))

        left = Emu(int((t.SLIDE_WIDTH - width) / 2))
        slide.shapes.add_picture(image_path, left, t.CONTENT_TOP, width=width, height=height)
    else:
        placeholder = slide.shapes.add_textbox(t.MARGIN, t.CONTENT_TOP, Inches(12), Inches(1))
        set_run(placeholder.text_frame.paragraphs[0], f"[이미지 없음: {image_path}]", color=t.TEXT_GRAY)

    if data.get("caption"):
        cap_box = slide.shapes.add_textbox(t.MARGIN, Inches(6.9), Inches(12), Inches(0.4))
        set_run(cap_box.text_frame.paragraphs[0], data["caption"], size=t.SIZE_CAPTION, color=t.TEXT_GRAY)

    return slide


# =========================
# 7. KPIDashboardSlide
# =========================
def render_kpi_dashboard_slide(prs: Presentation, data: Dict[str, Any], images_dir: str):
    """
    헤드라인 텍스트 + KPI 카드 여러 개(가로) + 이미지 2장(나란히).
    이미지는 _add_side_by_side_images() 공통 헬퍼로 배치한다.
    """
    slide = add_blank_slide(prs)
    add_header(slide, data.get("category_label", ""), data["title"])

    headline_box = slide.shapes.add_textbox(t.MARGIN, t.CONTENT_TOP, Inches(12), Inches(0.5))
    set_run(headline_box.text_frame.paragraphs[0], data["headline"], size=Pt(16), bold=True)

    cards = data["kpi_cards"]
    n = len(cards)
    gap = Inches(0.3)
    total_width = t.SLIDE_WIDTH - 2 * t.MARGIN
    card_width = Emu(int((total_width - gap * (n - 1)) / n))
    card_top = Inches(2.4)
    card_height = Inches(1.1)
    x = t.MARGIN

    for card in cards:
        box_shape = slide.shapes.add_shape(1, x, card_top, card_width, card_height)
        box_shape.fill.background()
        box_shape.line.color.rgb = t.LINE_BLACK
        box_shape.line.width = Pt(1.0)
        box_shape.shadow.inherit = False

        tf = box_shape.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.15)
        tf.margin_top = Inches(0.1)
        set_run(tf.paragraphs[0], card["value"], size=Pt(22), bold=True)
        p2 = tf.add_paragraph()
        set_run(p2, card["label"], size=Pt(11), color=t.TEXT_GRAY)

        x = Emu(x + card_width + gap)

    _add_side_by_side_images(slide, data["images"], images_dir, top=Inches(3.9), max_height=Inches(3.2))

    return slide


# =========================
# 8. ChartInsightSlide
# =========================
def render_chart_insight_slide(prs: Presentation, data: Dict[str, Any], images_dir: str):
    """
    왼쪽: 차트 이미지 1장 (비율 유지)
    오른쪽: insight_cards 여러 개 (세로로 쌓임, 라벨/값/detail)
    하단: key_insight 굵은 텍스트

    카드 개수와 무관하게 항상 정해진 영역(세로 4.3") 안에 들어가도록
    카드 개수에 맞춰 높이와 폰트 크기를 동적으로 계산한다. 이렇게
    해야 카드가 2개(Carrier Delivery)든 3개(Seller Processing)든
    슬라이드 밖으로 넘치거나 하단 텍스트와 겹치지 않는다.
    """
    slide = add_blank_slide(prs)
    add_header(slide, data.get("category_label", ""), data["title"])

    top = t.CONTENT_TOP
    if data.get("subtitle"):
        sub_box = slide.shapes.add_textbox(t.MARGIN, top, Inches(12), Inches(0.4))
        set_run(sub_box.text_frame.paragraphs[0], data["subtitle"], size=Pt(14), color=t.TEXT_GRAY)
        top = Emu(top + Inches(0.5))

    chart_area_width = Inches(7.0)
    chart_area_height = Inches(4.2)
    image_info = data["images"][0]
    image_path = str(Path(images_dir) / image_info["path"].replace("images/", ""))

    if Path(image_path).exists():
        from PIL import Image
        with Image.open(image_path) as img:
            img_w, img_h = img.size
        ratio = img_w / img_h
        if chart_area_width / ratio <= chart_area_height:
            width = chart_area_width
            height = Emu(int(chart_area_width / ratio))
        else:
            height = chart_area_height
            width = Emu(int(chart_area_height * ratio))
        slide.shapes.add_picture(image_path, t.MARGIN, top, width=width, height=height)

    card_x = Inches(8.2)
    card_width = t.SLIDE_WIDTH - t.MARGIN - card_x
    cards = data["insight_cards"]
    n_cards = len(cards)
    card_area_height = Inches(4.3)
    card_gap = Inches(0.2)
    card_height = Emu(int((card_area_height - card_gap * (n_cards - 1)) / n_cards))
    label_size = Pt(14) if n_cards <= 2 else Pt(12)
    value_size = Pt(18) if n_cards <= 2 else Pt(15)
    detail_size = Pt(10) if n_cards <= 2 else Pt(9)

    card_y = top
    for card in cards:
        box_shape = slide.shapes.add_shape(1, card_x, card_y, card_width, card_height)
        box_shape.fill.background()
        box_shape.line.color.rgb = t.LINE_BLACK
        box_shape.line.width = Pt(1.0)
        box_shape.shadow.inherit = False

        tf = box_shape.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.15)
        tf.margin_top = Inches(0.08)
        set_run(tf.paragraphs[0], card["label"], size=label_size, bold=True)
        p2 = tf.add_paragraph()
        set_run(p2, card["value"], size=value_size, bold=True, color=t.TEXT_GRAY)
        if card.get("detail"):
            p3 = tf.add_paragraph()
            set_run(p3, card["detail"], size=detail_size, color=t.TEXT_GRAY)

        card_y = Emu(card_y + card_height + card_gap)

    if data.get("key_insight"):
        ki_box = slide.shapes.add_textbox(t.MARGIN, Inches(6.6), Inches(12.1), Inches(0.8))
        ki_box.text_frame.word_wrap = True
        set_run(ki_box.text_frame.paragraphs[0], data["key_insight"], size=Pt(12), bold=True)

    return slide


# =========================
# 9. DualImageSlide
# =========================
def render_dual_image_slide(prs: Presentation, data: Dict[str, Any], images_dir: str):
    """이미지 2장(또는 그 이상)을 가로로 나란히 배치. _add_side_by_side_images() 재사용."""
    slide = add_blank_slide(prs)
    add_header(slide, data.get("category_label", ""), data["title"])
    _add_side_by_side_images(slide, data["images"], images_dir, top=t.CONTENT_TOP, max_height=Inches(4.8))
    return slide


# =========================
# 10. ExperimentSlide
# =========================
def render_experiment_slide(prs: Presentation, data: Dict[str, Any]):
    """
    좌우 2단 컬럼. 왼쪽은 key-value 형태(baseline, MDE 등),
    오른쪽은 treatment/control + success_criteria 리스트.
    """
    slide = add_blank_slide(prs)
    add_header(slide, data.get("category_label", ""), data["title"])

    top = t.CONTENT_TOP
    if data.get("subtitle"):
        sub_box = slide.shapes.add_textbox(t.MARGIN, top, Inches(12), Inches(0.4))
        set_run(sub_box.text_frame.paragraphs[0], data["subtitle"], size=Pt(16), bold=True)
        top = Emu(top + Inches(0.6))

    col_width = Inches(5.8)
    left_x = t.MARGIN
    right_x = Emu(int(t.SLIDE_WIDTH - t.MARGIN - col_width))

    left = data["left_column"]
    left_labels = {
        "primary_metric": "Primary Metric",
        "baseline": "Baseline",
        "mde": "MDE",
        "alpha_power": "Alpha / Power",
        "sample_size": "Sample Size",
        "experiment_unit": "Experiment Unit",
    }
    y = top
    for key, label in left_labels.items():
        if key not in left:
            continue
        box = slide.shapes.add_textbox(left_x, y, col_width, Inches(0.7))
        tf = box.text_frame
        tf.word_wrap = True
        set_run(tf.paragraphs[0], label, size=Pt(12), bold=True, color=t.TEXT_GRAY)
        p2 = tf.add_paragraph()
        set_run(p2, str(left[key]), size=Pt(15), bold=True)
        y = Emu(y + Inches(0.75))

    right = data["right_column"]
    y = top
    for key, label in (("treatment", "Treatment"), ("control", "Control")):
        box = slide.shapes.add_textbox(right_x, y, col_width, Inches(0.7))
        tf = box.text_frame
        tf.word_wrap = True
        set_run(tf.paragraphs[0], label, size=Pt(12), bold=True, color=t.TEXT_GRAY)
        p2 = tf.add_paragraph()
        set_run(p2, str(right[key]), size=Pt(14))
        y = Emu(y + Inches(0.75))

    y = Emu(y + Inches(0.2))
    sc_box = slide.shapes.add_textbox(right_x, y, col_width, Inches(0.4))
    set_run(sc_box.text_frame.paragraphs[0], "Success Criteria", size=Pt(12), bold=True, color=t.TEXT_GRAY)
    y = Emu(y + Inches(0.4))

    criteria_box = slide.shapes.add_textbox(right_x, y, col_width, Inches(2.0))
    tf = criteria_box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(right["success_criteria"]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(6)
        set_run(p, f"✓  {item}", size=Pt(12))

    return slide


# =========================
# 11. RoadmapSlide
# =========================
def render_roadmap_slide(prs: Presentation, data: Dict[str, Any]):
    """
    4단계(또는 N단계) 타임라인. 각 phase는 원형 번호 + 라벨 + 상태 + 설명으로
    구성되며, 가로로 나열해 진행 순서를 보여준다. status가 "Done"이면
    원을 채워서(검정) 완료를 표시하고, 그 외는 빈 원으로 표시한다.
    """
    slide = add_blank_slide(prs)
    add_header(slide, data.get("category_label", ""), data["title"])

    phases = data["phases"]
    n = len(phases)
    gap = Inches(0.4)
    total_width = t.SLIDE_WIDTH - 2 * t.MARGIN
    phase_width = Emu(int((total_width - gap * (n - 1)) / n))
    top = t.CONTENT_TOP
    circle_size = Inches(0.6)
    x = t.MARGIN

    line = slide.shapes.add_connector(
        1, Emu(int(t.MARGIN + circle_size / 2)), Emu(int(top + circle_size / 2)),
        Emu(int(t.SLIDE_WIDTH - t.MARGIN - circle_size / 2)), Emu(int(top + circle_size / 2)),
    )
    line.line.color.rgb = t.TABLE_BORDER
    line.line.width = Pt(1.5)

    for phase in phases:
        circle = slide.shapes.add_shape(9, x, top, circle_size, circle_size)  # 9 = OVAL
        circle.fill.solid()
        circle.fill.fore_color.rgb = t.TEXT_BLACK if phase["status"] == "Done" else t.BG_WHITE
        circle.line.color.rgb = t.TEXT_BLACK
        circle.line.width = Pt(1.5)
        circle.shadow.inherit = False
        num_color = t.BG_WHITE if phase["status"] == "Done" else t.TEXT_BLACK
        set_run(circle.text_frame.paragraphs[0], str(phase["number"]), size=Pt(16), bold=True, color=num_color)
        circle.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

        label_box = slide.shapes.add_textbox(x, Emu(top + circle_size + Inches(0.2)), phase_width, Inches(0.4))
        set_run(label_box.text_frame.paragraphs[0], phase["label"], size=Pt(14), bold=True)

        status_box = slide.shapes.add_textbox(x, Emu(top + circle_size + Inches(0.6)), phase_width, Inches(0.3))
        set_run(status_box.text_frame.paragraphs[0], phase["status"], size=Pt(11), color=t.TEXT_GRAY)

        detail_box = slide.shapes.add_textbox(x, Emu(top + circle_size + Inches(1.0)), phase_width, Inches(0.8))
        detail_box.text_frame.word_wrap = True
        set_run(detail_box.text_frame.paragraphs[0], phase["detail"], size=Pt(11), color=t.TEXT_GRAY)

        x = Emu(x + phase_width + gap)

    return slide


# =========================
# 12. ClosingSlide
# =========================
def render_closing_slide(prs: Presentation, data: Dict[str, Any]):
    """제목 + 서술 문단들(paragraphs) + 하단 콜아웃 카드(callouts)."""
    slide = add_blank_slide(prs)
    add_header(slide, data.get("category_label", ""), data["title"])

    top = t.CONTENT_TOP
    for para in data["paragraphs"]:
        p_box = slide.shapes.add_textbox(t.MARGIN, top, Inches(12.1), Inches(1.0))
        tf = p_box.text_frame
        tf.word_wrap = True
        set_run(tf.paragraphs[0], para, size=Pt(16))
        top = Emu(top + Inches(1.0))

    callouts = data["callouts"]
    n = len(callouts)
    gap = Inches(0.3)
    total_width = t.SLIDE_WIDTH - 2 * t.MARGIN
    callout_width = Emu(int((total_width - gap * (n - 1)) / n))
    callout_top = Inches(5.6)
    callout_height = Inches(1.3)
    x = t.MARGIN

    for callout in callouts:
        box_shape = slide.shapes.add_shape(1, x, callout_top, callout_width, callout_height)
        box_shape.fill.background()
        box_shape.line.color.rgb = t.LINE_BLACK
        box_shape.line.width = Pt(1.0)
        box_shape.shadow.inherit = False

        tf = box_shape.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.15)
        tf.margin_top = Inches(0.15)
        set_run(tf.paragraphs[0], callout["value"], size=Pt(24), bold=True)
        p2 = tf.add_paragraph()
        set_run(p2, callout["label"], size=Pt(11), color=t.TEXT_GRAY)

        x = Emu(x + callout_width + gap)

    return slide


# =========================
# 13. 레지스트리 + 전체 실행
# =========================
RENDERERS = {
    "TitleSlide": render_title_slide,
    "BigNumberSlide": render_big_number_slide,
    "DataTableSlide": render_data_table_slide,
    "SummaryCardSlide": render_summary_card_slide,
    "ImageSlide": render_image_slide,
    "KPIDashboardSlide": render_kpi_dashboard_slide,
    "ChartInsightSlide": render_chart_insight_slide,
    "DualImageSlide": render_dual_image_slide,
    "ExperimentSlide": render_experiment_slide,
    "RoadmapSlide": render_roadmap_slide,
    "ClosingSlide": render_closing_slide,
}


def run(report_data_path: str, output_path: str, images_dir: str) -> str:
    """
    report_data.json을 읽어 슬라이드를 순서대로 렌더링하고 pptx로 저장한다.

    Args:
        report_data_path: report_data.json 경로
        output_path: 저장할 .pptx 경로
        images_dir: report_data.json의 상대 image path 기준 폴더

    Returns:
        str: 저장된 pptx 경로
    """
    with open(report_data_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)

    prs = Presentation()
    prs.slide_width = t.SLIDE_WIDTH
    prs.slide_height = t.SLIDE_HEIGHT

    skipped = []
    for slide_data in report_data["slides"]:
        slide_type = slide_data["type"]
        renderer = RENDERERS.get(slide_type)
        if renderer is None:
            skipped.append(slide_type)
            continue
        if slide_type in IMAGE_SLIDE_TYPES:
            renderer(prs, slide_data, images_dir)
        else:
            renderer(prs, slide_data)

    prs.save(output_path)
    if skipped:
        print(f"[PPT] 아직 구현되지 않은 타입이라 건너뜀: {skipped}")
    print(f"[PPT] 저장 완료: {output_path}")
    return output_path


if __name__ == "__main__":
    run(
        report_data_path="report_data.json",
        output_path="executive_report_draft.pptx",
        images_dir="images",
    )