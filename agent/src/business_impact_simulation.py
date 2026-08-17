# business_impact_simulation.py
"""
⑤ Business Impact Simulation 모듈
- rootcause_report.json에서 threshold를 통과한 categorical 변수들에 대해
  각 그룹(예: customer_state의 각 주)별 Impact Score를 계산
- Impact Score = (그룹 평균 - 전체 평균) × 그룹 주문 건수
- 계산된 모든 시나리오 후보를 Impact Score 기준으로 정렬해 순위를 매김

설계 원칙: Impact Score는 범주형(categorical) 변수에만 적용한다.
연속형(continuous) 변수는 groupby 시 거의 모든 값이 유니크해 그룹 평균이
자기 자신이 되어버려 Impact Score 계산이 의미를 갖지 못한다. 연속형
변수의 binning 전략(equal-width, equal-frequency, domain-aware 등)은
변수 성격마다 최적 방식이 달라 일반화하기 어려우므로, 이번 구현에서는
범주형만 지원하고 연속형은 향후 확장 포인트로 남긴다.

노트북에서는 3개 변수(customer_state, carrier_month, product_category)를
먼저 사람이 선정한 뒤 Impact Score를 계산했다. Agent에서는 "몇 개를 볼지"를
사람이 미리 정하지 않고, ④ RCA에서 threshold(effect_size_pct >= 2%)를
통과한 모든 categorical 변수에 대해 Impact Score를 계산한 뒤, 그 결과값
자체로 최종 순위를 매기는 방식으로 표준화했다.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd
import matplotlib.pyplot as plt
from config import CONFIG_DIR, DATA_DIR, OUTPUT_DIR, ensure_dir, log
from join_engine import build_relationship_graph, find_join_path, build_analysis_dataset
from root_cause_analysis import (
    load_json, load_yaml, add_derived_columns, load_dataframes_for_join, find_base_table_name,
)


# =========================
# 1. Impact Score 계산 (범주형 전용)
# =========================
def calculate_impact_scores(
    df: pd.DataFrame, feature_col: str, kpi_col: str, min_count: int = 50
) -> pd.DataFrame:
    """
    범주형 변수의 각 그룹별로 Impact Score를 계산.
    Impact Score = (그룹 평균 - 전체 평균) × 그룹 주문 건수

    Args:
        df: 대상 DataFrame
        feature_col: 그룹핑할 범주형 변수 (예: "customer_state")
        kpi_col: KPI 컬럼 (예: "carrier_delivery_time")
        min_count: 최소 주문 건수 필터 (노트북에서 50건 이상만 본 것 재현)

    Returns:
        pd.DataFrame: 그룹별 avg_value, order_count, excess_hours,
        impact_score (impact_score 내림차순 정렬)
    """
    overall_mean = df[kpi_col].mean()

    stats = df.groupby(feature_col).agg(
        avg_value=(kpi_col, "mean"),
        order_count=(kpi_col, "count"),
    ).reset_index()

    stats = stats[stats["order_count"] >= min_count].copy()
    stats["excess_hours"] = stats["avg_value"] - overall_mean
    stats["impact_score"] = stats["excess_hours"] * stats["order_count"]

    return stats.sort_values("impact_score", ascending=False).reset_index(drop=True)


# =========================
# 2. 변수별 데이터셋 준비 (RCA의 join_engine 로직 재사용)
# =========================
def prepare_dataset_for_variable(
    variable: str,
    stage_key: str,
    processed_df: pd.DataFrame,
    data_dictionary: Dict[str, Any],
    approved_features_all: Dict[str, Any],
    data_dir: str,
) -> pd.DataFrame:
    """
    (docstring 동일, 생략)
    """
    approved_features = approved_features_all[stage_key]
    derived = approved_features.get("derived", {})

    if variable in derived:
        return add_derived_columns(processed_df, {variable: derived[variable]})

    base_table = find_base_table_name(data_dictionary, processed_df)

    target_table = None
    for table_name, table_info in data_dictionary.items():
        if table_name == "table_relationships":
            continue
        if variable in table_info.get("columns", {}):
            target_table = table_name
            break
    if target_table is None:
        raise ValueError(f"'{variable}'이 어느 테이블에도 없습니다.")

    graph = build_relationship_graph(data_dictionary["table_relationships"])
    join_path = find_join_path(base_table, target_table, graph)
    tables_needed = {step["to_table"] for step in join_path}

    raw_dataframes = load_dataframes_for_join(data_dir, list(tables_needed))
    raw_dataframes[base_table] = processed_df
    merged_df = build_analysis_dataset(
        raw_dataframes, base_table, [target_table], data_dictionary["table_relationships"]
    )
    return merged_df


# =========================
# 3. 시각화
# =========================
def plot_impact_scores(scenarios: List[Dict[str, Any]], output_path: str) -> None:
    """
    최종 선정된 시나리오들의 Impact Score bar chart 생성

    Args:
        scenarios: 시나리오 후보 리스트 (각 원소에 "label", "impact_score" 포함)
        output_path: 저장할 png 경로
    """
    df = pd.DataFrame(scenarios).sort_values("impact_score", ascending=False)
    plt.figure(figsize=(10, 5))
    plt.bar(df["label"], df["impact_score"])
    plt.xlabel("Scenario")
    plt.ylabel("Impact Score")
    plt.title("Business Impact Simulation - Scenario Ranking")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    log(f"impact_score 차트 저장 완료: {output_path}")


# =========================
# 4. 전체 실행 함수
# =========================
def run(
    config_dir: str = CONFIG_DIR,
    data_dir: str = DATA_DIR,
    output_dir: str = OUTPUT_DIR,
    top_n_per_variable: int = 3,
) -> Dict[str, str]:
    """
    ⑤ Business Impact Simulation 전체 실행:
    rootcause_report.json에서 threshold 통과한 categorical 변수들에 대해
    각각 Impact Score를 계산하고, 전체 시나리오를 Impact Score 기준으로
    정렬해 simulation_report.json + impact_score.png를 생성한다.

    Args:
        config_dir: approved_features.yaml이 있는 폴더
        data_dir: raw CSV 폴더 경로
        output_dir: rootcause_report.json, effect_size_report.json,
            processed_dataset.parquet 등이 있고 결과물을 저장할 폴더
        top_n_per_variable: 변수별로 상위 몇 개 그룹까지 시나리오 후보로
            남길지 (기본 3개, 노트북에서 head(10) 했던 것보다 보수적으로 설정)

    Returns:
        Dict[str, str]: 생성된 파일 경로들
    """
    output_dir = ensure_dir(output_dir)

    rootcause_report = load_json(str(Path(output_dir) / "rootcause_report.json"))
    effect_size_report = load_json(str(Path(output_dir) / "effect_size_report.json"))
    data_dictionary = load_json(str(Path(output_dir) / "data_dictionary.json"))
    approved_features_all = load_yaml(str(Path(config_dir) / "approved_features.yaml"))

    processed_path = Path(output_dir) / "processed_dataset.parquet"
    processed_df = pd.read_parquet(processed_path)

    # variable → type(categorical/continuous), stage_key, kpi_column 매핑 생성
    variable_meta = {}
    for stage_data in effect_size_report["stages"]:
        stage_key = stage_data["stage"].lower().replace(" ", "_")
        for e in stage_data["effect_sizes"]:
            variable_meta[e["variable"]] = {
                "type": e["type"],
                "stage_key": stage_key,
                "kpi_column": stage_data["kpi_column"],
                "effect_size_pct": e["effect_size_pct"],
            }

    all_scenarios = []
    for stage in rootcause_report["stages"]:
        for cause in stage.get("top_causes", []):
            # top_causes는 category 단위이므로, cause_effect_structure의
            # 개별 variable 목록이 필요 -> effect_size_report에서 이미
            # threshold를 통과한 variable 전체를 순회하는 방식으로 대체
            pass

    # cause_effect_structure_{stage}.json에서 threshold 통과한 개별 variable 목록 확보
    structure_files = list(Path(output_dir).glob("cause_effect_structure_*.json"))
    significant_variables = set()
    for f in structure_files:
        structure = load_json(str(f))
        for category in structure["categories"]:
            for cause in category["causes"]:
                significant_variables.add(cause["variable"])

    for variable in significant_variables:
        meta = variable_meta.get(variable)
        if meta is None:
            log(f"{variable}: effect_size_report에서 메타 정보를 찾지 못해 생략")
            continue
        if meta["type"] == "continuous":
            log(f"{variable}: 연속형 변수라 Impact Score 계산 생략 (향후 확장 포인트)")
            continue

        merged_df = prepare_dataset_for_variable(
            variable, meta["stage_key"], processed_df, data_dictionary, approved_features_all, data_dir
        )
        impact_df = calculate_impact_scores(merged_df, variable, meta["kpi_column"])

        for _, row in impact_df.head(top_n_per_variable).iterrows():
            all_scenarios.append({
                "variable": variable,
                "group": str(row[variable]),
                "label": f"{variable}={row[variable]}",
                "avg_hours": round(float(row["avg_value"]), 1),
                "order_count": int(row["order_count"]),
                "excess_hours": round(float(row["excess_hours"]), 1),
                "impact_score": round(float(row["impact_score"]), 0),
                "kpi_column": meta["kpi_column"],
                "effect_size_pct": meta["effect_size_pct"],
            })

    all_scenarios.sort(key=lambda s: s["impact_score"], reverse=True)

    simulation_report = {"scenarios": all_scenarios}
    report_path = Path(output_dir) / "simulation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(simulation_report, f, ensure_ascii=False, indent=2)
    log(f"simulation_report.json 저장 완료: {report_path} ({len(all_scenarios)}개 시나리오)")

    chart_path = Path(output_dir) / "impact_score.png"
    plot_impact_scores(all_scenarios[:10], str(chart_path))

    return {"simulation_report": str(report_path), "impact_score_chart": str(chart_path)}