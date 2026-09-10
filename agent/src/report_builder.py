# report_builder.py
"""
⑧ Report Builder 모듈
- bottleneck_report.json, rootcause_report.json, simulation_report.json,
  recommended_scenario.json, experiment_design_report.json과
  experiment_approval.yaml을 읽어서
  report_data.json(PPT Generator의 유일한 입력)으로 통합

역할 분리: 이 파일까지가 "이전 분석 결과물의 존재"를 아는 마지막
단계다. PPT Generator(⑨)는 이 파일이 만든 report_data.json만 읽고,
그 이전 파일들을 전혀 모른다.

LLM 호출 없음: 서술형 텍스트(summary, reason, expected_effect 등)는
이미 ④⑤⑥ 단계(RCA, Business Impact, Scenario Recommendation)에서
LLM이 생성해둔 값을 그대로 옮겨오기만 한다. 이 파일은 새로운 판단이나
해석을 만들지 않고, 기존 값들을 report_data.json 스키마에 맞게
재배열하는 순수 Python 로직이다.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List
import yaml
from config import OUTPUT_DIR, CONFIG_DIR, ensure_dir, log
from labels import build_value_formatters


# =========================
# 1. 로드 유틸
# =========================
def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_approved_scenario(recommended: Dict[str, Any], approval: Dict[str, Any]) -> Dict[str, Any]:
    """
    최종 보고서가 가리킬 시나리오를 "사람이 승인한 결과"에서 조회한다.

    recommended_scenario.json의 priority는 ⑥단계가 effect_size_pct 순으로
    자동 부여한 값이고, 실제 승인 결과는 사람이 작성한
    experiment_approval.yaml의 scenario_id다. 이 둘은 일치하지 않을 수 있다 — 통계적 설명력이 가장 큰
    원인과, 실제로 손댈 레버가 있는 원인은 다른 질문이기 때문이다.

    priority==1을 쓰면 사람이 S3를 승인해도 요약/결론 슬라이드는 S1을 가리켜
    한 덱에 권고가 두 개 실린다. 승인 결과를 단일 기준으로 삼아 이를 막는다.

    Args:
        recommended: recommended_scenario.json 내용
        approval: experiment_approval.yaml 내용 (Human Approval 결과)

    Returns:
        Dict[str, Any]: 승인된 시나리오

    Raises:
        ValueError: 승인된 id가 추천 목록에 없는 경우. 조용히 다른 시나리오를
            쓰는 대신 여기서 즉시 멈춘다.
    """
    approved_id = approval["scenario_id"]
    for s in recommended["recommended_scenarios"]:
        if s["id"] == approved_id:
            return s
    available = [s["id"] for s in recommended["recommended_scenarios"]]
    raise ValueError(
        f"experiment_approval.yaml이 승인한 시나리오 '{approved_id}'가 "
        f"recommended_scenario.json에 없습니다. (추천 목록: {available}) "
        f"⑥단계를 다시 실행했다면 승인 id를 확인하세요."
    )


# =========================
# 2. 슬라이드별 빌더 함수
# =========================
def build_title_slide(bottleneck_report: Dict[str, Any], recommended: Dict[str, Any]) -> Dict[str, Any]:
    """커버 슬라이드. 총 주문/지연율/추천 시나리오 개수만 옮긴다."""
    return {
        "type": "TitleSlide",
        "main_title": "Olist E-Commerce",
        "subtitle": "Delivery Process Bottleneck Analysis & Improvement Strategy",
        "meta": "Executive Report | Target: 물류 운영 책임자 및 경영진",
        "stat_cards": [
            {"value": f"{bottleneck_report['total_orders']:,} Orders", "label": "Analyzed"},
            {"value": f"{bottleneck_report['delay_rate_pct']}%", "label": "Delay Rate"},
            {"value": f"{len(recommended['recommended_scenarios'])} Scenarios", "label": "Recommended"},
        ],
    }


def build_summary_slide(
    bottleneck_report: Dict[str, Any], recommended: Dict[str, Any], approval: Dict[str, Any]
) -> Dict[str, Any]:
    """Executive Summary. 사람이 승인한 시나리오를 표시한다(자동 순위 아님)."""
    top_scenario = get_approved_scenario(recommended, approval)
    return {
        "type": "SummaryCardSlide",
        "title": "Executive Summary",
        "cards": [
            {"label": "Problem", "value": f"{bottleneck_report['delay_rate_pct']}%", "caption": "배송 지연율"},
            {"label": "Cause", "value": f"{bottleneck_report['bottlenecks'][0]}", "caption": "핵심 병목 구간"},
            {"label": "Top Priority", "value": top_scenario["id"], "caption": top_scenario["title"]},
            {"label": "Effect Size", "value": f"{top_scenario['effect_size_pct']}%", "caption": "1순위 원인 설명력"},
        ],
    }


def build_business_problem_slide(bottleneck_report: Dict[str, Any]) -> Dict[str, Any]:
    """Business Problem. stage_summary와 delayed_vs_normal을 표로 결합한다."""
    # 반올림된 비율로 역산하면 실제 건수와 어긋난다 (95,082 x 8.2% = 7,797 vs 실제 7,792).
    # ③단계가 저장한 실제 건수를 쓰고, 예전 산출물이라 키가 없으면 역산으로 대체한다.
    delay_count = bottleneck_report.get("delayed_orders") or round(
        bottleneck_report["total_orders"] * bottleneck_report["delay_rate_pct"] / 100
    )
    rows = []
    for d in bottleneck_report["delayed_vs_normal"]:
        rows.append([d["stage_name"], d["delayed_avg_hours"], d["normal_avg_hours"], f"{d['ratio']}x"])

    return {
        "type": "BigNumberSlide",
        "title": "Business Problem",
        "big_number": f"{delay_count:,}건",
        "context": f"전체 {bottleneck_report['total_orders']:,}건 주문 중",
        "highlight": f"배송 지연 발생 (지연율 {bottleneck_report['delay_rate_pct']}%)",
        "table": {
            "headers": ["Stage", "Delayed (h)", "Normal (h)", "Ratio"],
            "rows": rows,
        },
        "footnote": "Business Risk: 고객 경험 저하 · 브랜드 신뢰도 하락 · 운영 비용 증가",
    }


def build_process_modeling_slide() -> Dict[str, Any]:
    """
    Process Modeling (BPMN). bpmn.png는 Agent가 생성하지 않고
    Human이 미리 준비해 config 폴더에 넣어둔 파일을 그대로 참조한다.
    """
    return {
        "type": "ImageSlide",
        "title": "Process Modeling (BPMN)",
        "images": [{"path": "images/bpmn.png", "caption": None}],
        "caption": "각 구간별 병목 발생 가능성을 가설로 설정 → Bottleneck Detection으로 검증",
    }


def build_bottleneck_slide(bottleneck_report: Dict[str, Any]) -> Dict[str, Any]:
    """Bottleneck Detection. stage_summary 전체를 KPI 카드로 나열한다."""
    primary = bottleneck_report["stage_summary"][0]
    headline = (
        f"{primary['stage_name']} {primary['share_pct']}% of Total Lead Time | "
        f"지연 주문에서 {next(d['ratio'] for d in bottleneck_report['delayed_vs_normal'] if d['stage_name'] == primary['stage_name'])}배 증가"
    )
    kpi_cards = [
        {"value": f"{s['share_pct']}%", "label": f"{s['stage_name']} · avg {s['avg_hours']}h"}
        for s in bottleneck_report["stage_summary"]
    ]
    return {
        "type": "KPIDashboardSlide",
        "title": "Bottleneck Detection",
        "headline": headline,
        "kpi_cards": kpi_cards,
        "images": [
            {"path": "images/stage_time_chart.png", "caption": None},
            {"path": "images/delayed_vs_normal.png", "caption": None},
        ],
    }


def build_rca_slide(stage_data: Dict[str, Any], stage_key: str, subtitle: str) -> Dict[str, Any]:
    """
    Root Cause Analysis. rootcause_report.json의 top_causes와 summary를
    그대로 옮긴다. summary는 이미 Step 3(LLM)이 생성해둔 값이다.
    """
    return {
        "type": "ChartInsightSlide",
        "layout": "left_chart_right_cards",
        "title": f"Root Cause Analysis — {stage_data['stage'].replace('_', ' ').title()}",
        "subtitle": subtitle,
        "images": [{"path": f"images/effect_size_{stage_key}.png", "caption": None}],
        "insight_cards": [
            {
                "label": c["category"],
                "value": f"η²={c['effect_size_pct']}%",
                "detail": c["explanation"],
            }
            for c in stage_data["top_causes"]
        ],
        "key_insight": stage_data["summary"],
    }


def build_cause_effect_slide(rootcause_report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cause-Effect Diagrams. rootcause_report.json의 stage 목록을 순회해
    cause_effect_diagram_{stage}.png 경로를 자동으로 생성한다.
    stage가 2개든 5개든 이 함수는 그대로 동작한다.
    """
    images = []
    for stage_data in rootcause_report["stages"]:
        stage_key = stage_data["stage"]
        images.append({
            "path": f"images/cause_effect_diagram_{stage_key}.png",
            "caption": stage_data["stage"].replace("_", " ").title(),
        })
    return {
        "type": "DualImageSlide",
        "title": "Cause-Effect Diagrams",
        "images": images,
        "footnote": "※ 카테고리와 η²는 ④단계 계산값. 각 카테고리 아래의 세부 원인(details)은 LLM이 "
                    "도메인 지식으로 생성한 가설이며 이 데이터로 검증되지 않았음. "
                    "인과 판단이 필요한 산출물은 자동화 대상에서 제외한다는 원칙에 따라 검증 없이 게시함.",
    }


def format_scenario_label(
    scenario: Dict[str, Any], display_names: Dict[str, str], formatters: Dict[str, Any]
) -> str:
    """
    simulation_report의 후보 하나를 사람이 읽는 라벨로 바꾼다.
    "carrier_month=3.0" → "배송 월 = 3월", "customer_state=RJ" → "고객 주(州) = RJ".

    Args:
        scenario: simulation_report.json의 scenarios 원소 (variable, group 포함)
        display_names: approved_features.yaml의 display_names
        formatters: build_value_formatters()의 결과

    Returns:
        str: 표시용 라벨
    """
    var, group = scenario["variable"], scenario["group"]
    name = display_names.get(var, var)
    fmt = formatters.get(var)
    value = fmt(group) if fmt else str(group).replace("_", " ").title() if var.endswith("_english") else str(group)
    return f"{name} = {value}"


def build_business_impact_slide(
    simulation_report: Dict[str, Any], approved_features_all: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Impact Score Ranking. simulation_report.json의 전체 후보를 Impact Score
    내림차순으로 정렬해 표로 만든다.

    제목을 "Business Impact Simulation"에서 바꿨다. 이 단계는 지연율 변화를
    시뮬레이션하지 않는다 — "시간 단축 → 지연율 감소"는 검증되지 않은
    가정이라 의도적으로 자동화에서 제외했고, Impact Score 산출까지만 한다.
    슬라이드 제목이 하지 않는 일을 주장하면 안 된다.

    원시 컬럼명(customer_state=RJ, carrier_month=3.0)은 경영진 대상 덱에
    노출하지 않고 display_names와 값 포맷터로 사람 언어로 바꾼다.
    """
    display_names = approved_features_all.get("display_names", {})
    formatters = build_value_formatters(approved_features_all)
    scenarios = sorted(simulation_report["scenarios"], key=lambda s: s["impact_score"], reverse=True)
    rows = [
        [
            format_scenario_label(s, display_names, formatters),
            f"{s['order_count']:,}건",
            f"{s.get('effect_size_pct', '-')}%",
            f"{s['impact_score']:,.0f}",
        ]
        for s in scenarios
    ]
    return {
        "type": "DataTableSlide",
        "title": "Impact Score Ranking",
        "subtitle": "전체 후보 — Effect Size(원인의 설명력) + Impact Score(개선 시 기대 효과)",
        "table": {
            "headers": ["Scenario", "Orders", "Effect Size", "Impact Score"],
            "rows": rows,
        },
        "key_insight": "Root Cause의 설명력(Effect Size)과 Business Impact(Impact Score)는 다른 질문에 답한다",
        "footnote": "※ Impact Score = (그룹 평균 − 전체 평균) × 주문 건수. 개선 우선순위 지표이며 실제 절감 시간이 아님. "
                    "지연율 변화 시뮬레이션은 검증되지 않은 가정에 기반하므로 의도적으로 수행하지 않음.",
    }


def build_recommendation_slide(recommended: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recommended Scenarios. recommended_scenario.json 전체를
    priority(=effect_size_pct) 순서 그대로 표로 옮긴다.
    Reason은 표에 넣지 않는다 (RCA/Cause-Effect 슬라이드에 이미
    서술되어 있어 중복이며, 긴 텍스트가 표를 슬라이드 밖으로
    밀어내는 문제도 방지한다).
    """
    rows = [
        [
            s["id"],
            s["title"],
            f"{s['effect_size_pct']}%",
            f"{s['impact_score']:,.0f}",
        ]
        for s in sorted(recommended["recommended_scenarios"], key=lambda s: s["priority"])
    ]
    return {
        "type": "DataTableSlide",
        "title": "Recommended Scenarios",
        "table": {
            "headers": ["ID", "Title", "Effect Size", "Impact Score"],
            "rows": rows,
        },
    }

def build_ab_test_slide(
    approval: Dict[str, Any], design: Dict[str, Any], approved_scenario: Dict[str, Any]
) -> Dict[str, Any]:
    """
    A/B Test Design. 사람의 판단(experiment_approval.yaml)과 ⑦단계의 계산
    결과(experiment_design_report.json)를 좌/우 컬럼으로 합친다.

    왼쪽(계산): 지표, baseline, MDE, 표본 수, 실험 단위와 Design Effect
    오른쪽(판단): 처치, 대조, 성공 기준
    각주: ⑦단계의 실행 가능성 판정

    baseline/mde는 지표 유형(연속형/비율형)에 중립적인 키를 읽는다.
    이전 구현은 `delay_rate_pct`, `value_pct`처럼 비율형 전용 키를
    하드코딩해, 1차 지표를 연속형으로 바꾸면 KeyError가 났다.
    """
    baseline, selected = design["baseline"], design["selected_design"]
    power, feasibility = design["power_analysis"], design["feasibility"]
    unit, metric_unit = selected["mde_unit"], baseline["metric_unit"]
    target_value = round(baseline["metric_mean"] - selected["mde"], 2)
    groups = ", ".join(baseline["target_values"])

    return {
        "type": "ExperimentSlide",
        "title": "A/B Test Design",
        "subtitle": f"{approved_scenario['id']}: {approved_scenario['title']}",
        "left_column": {
            "primary_metric": selected["metric"],
            "baseline": f"{baseline['metric_mean']} {metric_unit} ({groups} 기준)",
            "mde": f"{selected['mde']} {unit} → Target {target_value} {metric_unit} "
                   f"(상대 {selected['relative_pct']}%)",
            "alpha_power": f"α={power['alpha']} / Power={power['power']} ({power['sided']})",
            "sample_size": f"{selected['sample_size_total']:,}건 "
                           f"(그룹당 {selected['sample_size_per_group']:,}건)",
            "experiment_unit": f"{selected['experiment_unit']} "
                               f"(Design Effect {selected['design_effect']})",
        },
        "right_column": {
            "treatment": approval["treatment"],
            "control": approval["control"],
            "success_criteria": approval["success_criteria"],
        },
        "footnote": f"실행 가능성 판정: {feasibility['status']} — {feasibility['message']} "
                    f"(대상 트래픽 하루 {baseline['estimated_daily_orders']}건 기준)",
    }


def build_roadmap_slide() -> Dict[str, Any]:
    """
    Implementation Roadmap. 4단계는 파이프라인 구조상 고정되어 있어
    (분석완료 → A/B Test → 검증 → 확대) 별도 입력 파일 없이 구성한다.
    """
    return {
        "type": "RoadmapSlide",
        "title": "Implementation Roadmap",
        "phases": [
            {"number": 1, "label": "Analysis Complete", "status": "Done", "detail": "1~8단계 분석 완료"},
            {"number": 2, "label": "A/B Test", "status": "Next", "detail": "1순위 시나리오 실험 설계"},
            {"number": 3, "label": "Validation", "status": "Pending", "detail": "통계적 유의성 검증"},
            {"number": 4, "label": "Full Deployment", "status": "Pending", "detail": "전사 확대 적용"},
        ],
    }


def build_closing_slide(
    bottleneck_report: Dict[str, Any], recommended: Dict[str, Any],
    approval: Dict[str, Any], design: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Final Recommendation. 사람이 승인한 시나리오와 병목 비중, 필요 샘플 수를
    콜아웃으로 다시 요약한다.

    결론 문장은 "effect size가 가장 크므로 이것을 하라"로 고정하지 않는다.
    통계적 설명력이 큰 원인과 실제로 손댈 레버가 있는 원인은 다를 수 있고,
    그 판단은 사람이 experiment_approval.yaml의 selection_reason에 남긴다.

    마지막 콜아웃은 표본 수가 아니라 "예상 실험 기간"으로 둔다. 필요 표본
    수만으로는 그 실험이 현실적인지 알 수 없고, 의사결정에 필요한 정보는
    "언제 답이 나오는가"이기 때문이다.
    """
    top_scenario = get_approved_scenario(recommended, approval)
    primary_stage = bottleneck_report["stage_summary"][0]
    selected = design["selected_design"]

    paragraphs = [
        f"{primary_stage['stage_name']}가 전체 리드타임의 {primary_stage['share_pct']}%를 차지하는 "
        f"핵심 병목으로 확인되었습니다.",
        f"검토된 {len(recommended['recommended_scenarios'])}개 시나리오 중 "
        f"{top_scenario['id']}({top_scenario['title']})을 A/B Test 검증 대상으로 승인했습니다.",
    ]
    selection_reason = str(approval.get("selection_reason", "")).strip()
    if selection_reason:
        paragraphs.append(f"선정 근거: {selection_reason}")

    return {
        "type": "ClosingSlide",
        "title": "Final Recommendation",
        "paragraphs": paragraphs,
        "callouts": [
            {"value": f"{primary_stage['share_pct']}%", "label": f"{primary_stage['stage_name']} 핵심 병목 비중"},
            {"value": f"{top_scenario['effect_size_pct']}%", "label": f"{top_scenario['variable']} Effect Size"},
            {"value": f"{selected['estimated_duration_days']}일", "label": "A/B Test 예상 기간"},
        ],
    }


# =========================
# 3. 전체 실행 함수
# =========================
def run(output_dir: str = OUTPUT_DIR, config_dir: str = CONFIG_DIR) -> Dict[str, str]:
    """
    ⑧ Report Builder 전체 실행: 5개 산출물을 읽어 report_data.json 생성

    Args:
        output_dir: bottleneck_report.json 등 4개 JSON이 있고 결과물을
            저장할 폴더
        config_dir: experiment_approval.yaml이 있는 폴더 (Human이 직접
            작성한 승인/판단 파일은 config에 위치)

    Returns:
        Dict[str, str]: 생성된 파일 경로
    """
    output_dir = ensure_dir(output_dir)

    bottleneck_report = load_json(str(Path(output_dir) / "bottleneck_report.json"))
    rootcause_report = load_json(str(Path(output_dir) / "rootcause_report.json"))
    simulation_report = load_json(str(Path(output_dir) / "simulation_report.json"))
    recommended = load_json(str(Path(output_dir) / "recommended_scenario.json"))
    approval = load_yaml(str(Path(config_dir) / "experiment_approval.yaml"))
    approved_features_all = load_yaml(str(Path(config_dir) / "approved_features.yaml"))
    design = load_json(str(Path(output_dir) / "experiment_design_report.json"))

    stage_subtitles = {
        idx: f"{'1st' if idx == 0 else '2nd'} Bottleneck | Lead Time {s['share_pct']}%"
        for idx, s in enumerate(bottleneck_report["stage_summary"][:2])
    }

    rca_slides = []
    for idx, stage_data in enumerate(rootcause_report["stages"]):
        stage_key = stage_data["stage"]
        subtitle = stage_subtitles.get(idx, "")
        rca_slides.append(build_rca_slide(stage_data, stage_key, subtitle))

    approved_scenario = get_approved_scenario(recommended, approval)

    report_data = {
        "slides": [
            build_title_slide(bottleneck_report, recommended),
            build_summary_slide(bottleneck_report, recommended, approval),
            build_business_problem_slide(bottleneck_report),
            build_process_modeling_slide(),
            build_bottleneck_slide(bottleneck_report),
            *rca_slides,
            build_cause_effect_slide(rootcause_report),
            build_business_impact_slide(simulation_report, approved_features_all),
            build_recommendation_slide(recommended),
            build_ab_test_slide(approval, design, approved_scenario),
            build_roadmap_slide(),
            build_closing_slide(bottleneck_report, recommended, approval, design),
        ]
    }

    report_path = Path(output_dir) / "report_data.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    log(f"report_data.json 저장 완료: {report_path} ({len(report_data['slides'])}개 슬라이드)")

    return {"report_data": str(report_path)}