# report_builder.py
"""
⑨-1 Report Builder 모듈
- bottleneck_report.json, rootcause_report.json, simulation_report.json,
  recommended_scenario.json, ab_test_design.yaml을 읽어서
  report_data.json(PPT Generator의 유일한 입력)으로 통합

역할 분리: 이 파일까지가 "이전 5개 분석 결과물의 존재"를 아는 마지막
단계다. PPT Generator(⑨-2)는 이 파일이 만든 report_data.json만 읽고,
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


# =========================
# 1. 로드 유틸
# =========================
def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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


def build_summary_slide(bottleneck_report: Dict[str, Any], recommended: Dict[str, Any]) -> Dict[str, Any]:
    """Executive Summary. 1순위 시나리오(priority=1)를 자동으로 찾아 표시한다."""
    top_scenario = next(s for s in recommended["recommended_scenarios"] if s["priority"] == 1)
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
    delay_count = round(
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
    }


def build_business_impact_slide(simulation_report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Business Impact Simulation. simulation_report.json의 전체 시나리오를
    Impact Score 내림차순으로 정렬해 표로 만든다.
    """
    scenarios = sorted(simulation_report["scenarios"], key=lambda s: s["impact_score"], reverse=True)
    rows = [
        [s["label"], s.get("effect_size_pct", "-"), f"{s['impact_score']:,.0f}"]
        for s in scenarios
    ]
    return {
        "type": "DataTableSlide",
        "title": "Business Impact Simulation",
        "subtitle": "전체 후보 — Effect Size + Impact Score",
        "table": {
            "headers": ["Scenario", "Effect Size", "Impact Score"],
            "rows": rows,
        },
        "key_insight": "Root Cause의 설명력(Effect Size)과 Business Impact(Impact Score)는 다를 수 있다",
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

def build_ab_test_slide(ab_test: Dict[str, Any]) -> Dict[str, Any]:
    """
    A/B Test Design. ab_test_design.yaml의 값을 그대로 좌/우 컬럼으로
    나눠 옮긴다.
    """
    return {
        "type": "ExperimentSlide",
        "title": "A/B Test Design",
        "subtitle": f"{ab_test['scenario']['id']}: {ab_test['scenario']['title']}",
        "left_column": {
            "primary_metric": ab_test["metrics"]["primary"],
            "baseline": f"{ab_test['baseline']['delay_rate_pct']}% ({ab_test['baseline']['target_group']} 기준)",
            "mde": f"{ab_test['mde']['value_pct']}%p → Target {ab_test['mde']['target_delay_rate_pct']}%",
            "alpha_power": f"α={ab_test['power_analysis']['alpha']} / Power={ab_test['power_analysis']['power']}",
            "sample_size": f"{ab_test['power_analysis']['sample_size_total']:,}건 (그룹당 {ab_test['power_analysis']['sample_size_per_group']:,}건)",
            "experiment_unit": ab_test["experiment_unit"],
        },
        "right_column": {
            "treatment": ab_test["treatment"],
            "control": ab_test["control"],
            "success_criteria": ab_test["success_criteria"],
        },
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


def build_closing_slide(bottleneck_report: Dict[str, Any], recommended: Dict[str, Any], ab_test: Dict[str, Any]) -> Dict[str, Any]:
    """
    Final Recommendation. 1순위 시나리오와 병목 비중, 필요 샘플 수를
    콜아웃으로 다시 요약한다.
    """
    top_scenario = next(s for s in recommended["recommended_scenarios"] if s["priority"] == 1)
    primary_stage = bottleneck_report["stage_summary"][0]
    return {
        "type": "ClosingSlide",
        "title": "Final Recommendation",
        "paragraphs": [
            f"{top_scenario['variable']}이 배송 지연의 가장 중요한 통계적 원인"
            f"(effect size {top_scenario['effect_size_pct']}%)으로 확인되었습니다.",
            f"따라서 {top_scenario['id']}({top_scenario['title']})을 우선적으로 A/B Test를 통해 검증한 후, "
            f"효과가 확인되면 전사 확대 적용을 권고합니다.",
        ],
        "callouts": [
            {"value": f"{primary_stage['share_pct']}%", "label": f"{primary_stage['stage_name']} 핵심 병목 비중"},
            {"value": f"{top_scenario['effect_size_pct']}%", "label": f"{top_scenario['variable']} Effect Size"},
            {"value": f"{ab_test['power_analysis']['sample_size_total']:,}건", "label": "A/B Test 필요 샘플 수"},
        ],
    }


# =========================
# 3. 전체 실행 함수
# =========================
def run(output_dir: str = OUTPUT_DIR, config_dir: str = CONFIG_DIR) -> Dict[str, str]:
    """
    ⑨-1 Report Builder 전체 실행: 5개 산출물을 읽어 report_data.json 생성

    Args:
        output_dir: bottleneck_report.json 등 4개 JSON이 있고 결과물을
            저장할 폴더
        config_dir: ab_test_design.yaml이 있는 폴더 (Human이 직접 작성한
            A/B Test 설계는 config에 위치)

    Returns:
        Dict[str, str]: 생성된 파일 경로
    """
    output_dir = ensure_dir(output_dir)

    bottleneck_report = load_json(str(Path(output_dir) / "bottleneck_report.json"))
    rootcause_report = load_json(str(Path(output_dir) / "rootcause_report.json"))
    simulation_report = load_json(str(Path(output_dir) / "simulation_report.json"))
    recommended = load_json(str(Path(output_dir) / "recommended_scenario.json"))
    ab_test = load_yaml(str(Path(config_dir) / "ab_test_design.yaml"))

    stage_subtitles = {
        idx: f"{'1st' if idx == 0 else '2nd'} Bottleneck | Lead Time {s['share_pct']}%"
        for idx, s in enumerate(bottleneck_report["stage_summary"][:2])
    }

    rca_slides = []
    for idx, stage_data in enumerate(rootcause_report["stages"]):
        stage_key = stage_data["stage"]
        subtitle = stage_subtitles.get(idx, "")
        rca_slides.append(build_rca_slide(stage_data, stage_key, subtitle))

    report_data = {
        "slides": [
            build_title_slide(bottleneck_report, recommended),
            build_summary_slide(bottleneck_report, recommended),
            build_business_problem_slide(bottleneck_report),
            build_process_modeling_slide(),
            build_bottleneck_slide(bottleneck_report),
            *rca_slides,
            build_cause_effect_slide(rootcause_report),
            build_business_impact_slide(simulation_report),
            build_recommendation_slide(recommended),
            build_ab_test_slide(ab_test),
            build_roadmap_slide(),
            build_closing_slide(bottleneck_report, recommended, ab_test),
        ]
    }

    report_path = Path(output_dir) / "report_data.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    log(f"report_data.json 저장 완료: {report_path} ({len(report_data['slides'])}개 슬라이드)")

    return {"report_data": str(report_path)}