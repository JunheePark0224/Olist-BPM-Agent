# experiment_design.py
"""
⑦ Experiment Design 모듈
- experiment_approval.yaml(사람의 판단)에서 승인된 시나리오와 처치를 읽어
- 그 시나리오의 baseline, 필요 표본 수, 랜덤화 단위별 ICC/Design Effect,
  예상 실험 기간, 가드레일 기준선을 계산해 experiment_design_report.json 생성
- LLM 호출 없음 (순수 Python/pandas/scipy 계산)

역할 분리 — 이 단계가 존재하는 이유:
    실험 설계에는 계산할 수 있는 것과 판단해야 하는 것이 섞여 있다.

    판단(사람):  처치가 무엇인가, 어떤 단위로 적용 가능한가,
                 얼마나 개선되면 의미가 있는가(MDE), 무엇을 지켜야 하는가
    계산(여기):  그 선택의 비용은 얼마인가 — 표본 수, 실험 기간,
                 클러스터 랜덤화 시 손해(Design Effect)

    이전 구현에서는 두 가지가 ab_test_design.yaml 한 파일에 섞여 있었고,
    계산 결과는 사람이 손으로 전사했다. 그래서 데이터가 바뀌거나 다른
    시나리오를 승인해도 숫자가 조용히 낡았다. 이 단계는 계산 부분을
    산출물로 분리해 그 전사를 없앤다.

실행 가능성 판정:
    kpi_definition.yaml의 experiment_policy.max_duration_days를 넘으면
    infeasible로 표시하고, 대안(지표 유형 변경 / MDE 상향)을 함께 계산해
    제시한다. bottleneck_policy가 병목 판정을 규칙화한 것과 같은 방식으로,
    "이 실험은 현실적인가"를 사람의 눈치가 아니라 임계값으로 판정한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from config import CONFIG_DIR, DATA_DIR, OUTPUT_DIR, ensure_dir, log
from root_cause_analysis import load_json, load_yaml
from business_impact_simulation import prepare_dataset_for_variable

# =========================
# 1. 승인된 시나리오 해석
# =========================
def resolve_target(
    approval: Dict[str, Any],
    recommended: Dict[str, Any],
    simulation_report: Dict[str, Any],
    effect_size_report: Dict[str, Any],
    kpi_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    사람이 승인한 시나리오 id로부터 분석 대상(변수, 값 목록, KPI, 구간)을 해석한다.

    시나리오는 여러 값을 묶을 수 있다(예: Carnival = carrier_month 2월+3월).
    따라서 대상은 단일 값이 아니라 값의 집합이다.

    Args:
        approval: experiment_approval.yaml 내용
        recommended: recommended_scenario.json 내용
        simulation_report: simulation_report.json 내용
        effect_size_report: effect_size_report.json 내용
        kpi_config: kpi_definition.yaml 내용 (구간의 표시용 이름을 얻기 위함)

    Returns:
        Dict[str, Any]: id, title, metric_label, variable, target_values,
        kpi_column, stage_key

    Raises:
        ValueError: 승인 id를 추천 목록에서 찾을 수 없는 경우
    """
    approved_id = approval["scenario_id"]
    scenario = next(
        (s for s in recommended["recommended_scenarios"] if s["id"] == approved_id), None
    )
    if scenario is None:
        available = [s["id"] for s in recommended["recommended_scenarios"]]
        raise ValueError(
            f"experiment_approval.yaml이 승인한 '{approved_id}'가 "
            f"recommended_scenario.json에 없습니다. (추천 목록: {available})"
        )

    variable = scenario["variable"]
    # included_values는 "carrier_month=2.0" 형태의 label이다.
    # simulation_report에 이미 파싱된 group/kpi_column이 있으므로 그것을 쓴다.
    by_label = {c["label"]: c for c in simulation_report["scenarios"]}
    target_values, kpi_column = [], None
    for label in scenario["included_values"]:
        candidate = by_label.get(label)
        if candidate is None:
            raise ValueError(f"시나리오 {approved_id}의 '{label}'을 simulation_report에서 찾을 수 없습니다.")
        target_values.append(str(candidate["group"]))
        kpi_column = candidate["kpi_column"]

    stage_key = next(
        s["stage"].lower().replace(" ", "_")
        for s in effect_size_report["stages"]
        if s["kpi_column"] == kpi_column
    )
    # 경영진 대상 덱에 원시 컬럼명이 노출되지 않도록, kpi_definition.yaml이
    # 정의한 사람이 읽는 구간 이름을 함께 실어둔다.
    metric_label = next(
        (p["name"] for p in kpi_config.get("processes", []) if p.get("kpi_column") == kpi_column),
        kpi_column,
    )

    log(f"승인 시나리오 {approved_id}: {variable} in {target_values} → KPI {kpi_column}")
    return {
        "id": approved_id,
        "title": scenario["title"],
        "metric_label": metric_label,
        "variable": variable,
        "target_values": target_values,
        "kpi_column": kpi_column,
        "stage_key": stage_key,
        "effect_size_pct": scenario["effect_size_pct"],
        "impact_score": scenario["impact_score"],
    }


# =========================
# 2. 대상 데이터셋 준비
# =========================
def attach_cluster_sources(df: pd.DataFrame, sources: List[Dict[str, Any]], data_dir: str) -> pd.DataFrame:
    """
    랜덤화 단위 후보에 필요한 컬럼을 주문 단위(grain)를 유지하며 붙인다.

    order_items처럼 주문당 여러 행을 갖는 테이블을 그대로 조인하면 행이
    복제되어 이후 모든 통계가 왜곡된다(노트북에서 실제로 발생했던 버그).
    `reduce: first`가 지정된 소스는 join_on 기준 첫 행만 남겨 주문 1행:1행을
    보장한 뒤 병합한다.

    Args:
        df: 대상 DataFrame
        sources: experiment_policy.cluster_sources
        data_dir: raw CSV 폴더

    Returns:
        pd.DataFrame: 컬럼이 추가된 DataFrame (행 수 불변)
    """
    out = df
    for spec in sources:
        path = Path(data_dir) / spec["file"]
        key = spec["join_on"]
        if not path.exists() or key not in out.columns:
            log(f"cluster_source 건너뜀: {spec['file']} (파일 없음 또는 조인 키 '{key}' 부재)")
            continue

        raw = pd.read_csv(path)
        wanted = [c for c in spec["columns"] if c in raw.columns]
        if not wanted:
            continue

        if spec.get("reduce") == "first":
            raw = raw.drop_duplicates(subset=[key], keep="first")

        before = len(out)
        out = out.merge(raw[[key] + wanted], on=key, how="left")
        if len(out) != before:
            raise ValueError(
                f"cluster_source '{spec['file']}' 조인으로 행 수가 {before:,} → {len(out):,}로 "
                f"변했습니다. 주문 단위 grain이 깨졌으므로 reduce 설정을 확인하세요."
            )
    return out


def add_cluster_columns(df: pd.DataFrame, candidates: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    experiment_policy에 정의된 랜덤화 단위 후보 컬럼을 준비한다.

    `column`이면 이미 있는 컬럼을 그대로 쓰고, `derive`면 원본 컬럼에서
    파생시킨다(예: 우편번호 앞 3자리). 필요한 원본 컬럼이 없으면 조용히
    건너뛴다 — 그 단위는 이 데이터셋에서 평가 불가라는 뜻이다.

    Args:
        df: 대상 주문 DataFrame
        candidates: experiment_policy.randomization_unit_candidates

    Returns:
        pd.DataFrame: 클러스터 컬럼이 추가된 DataFrame
    """
    out = df.copy()
    for cand in candidates:
        name = cand["name"]
        if "column" in cand:
            continue  # 원본 컬럼을 그대로 사용
        derive = cand.get("derive")
        if not derive or derive["source"] not in out.columns:
            continue
        source = out[derive["source"]].astype(str).str.zfill(derive.get("zfill", 0))
        out[name] = source.str[: derive["prefix_length"]]
    return out


def build_target_dataset(
    target: Dict[str, Any],
    processed_df: pd.DataFrame,
    data_dictionary: Dict[str, Any],
    approved_features_all: Dict[str, Any],
    policy: Dict[str, Any],
    data_dir: str,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    대상 변수를 붙인 전체 데이터셋과, 그중 시나리오 대상 그룹만 남긴
    DataFrame을 만든다.

    변수가 파생 컬럼이면 생성하고, 다른 테이블에 있으면 join_engine으로
    조인한다. 이 로직은 ⑤ Business Impact Simulation과 동일하므로 재사용한다.

    Args:
        target: resolve_target()의 결과
        processed_df: processed_dataset.parquet
        data_dictionary: data_dictionary.json
        approved_features_all: approved_features.yaml
        policy: experiment_policy
        data_dir: raw CSV 폴더

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame]: (전체, 대상 그룹만)
    """
    merged = prepare_dataset_for_variable(
        target["variable"], target["stage_key"], processed_df,
        data_dictionary, approved_features_all, data_dir,
    )
    merged = attach_cluster_sources(merged, policy.get("cluster_sources", []), data_dir)
    merged = add_cluster_columns(merged, policy.get("randomization_unit_candidates", []))
    merged["_metric_days"] = merged[target["kpi_column"]] / policy["kpi_hours_per_unit"]

    mask = merged[target["variable"]].astype(str).isin(target["target_values"])
    subset = merged[mask].copy()
    if subset.empty:
        raise ValueError(
            f"대상 그룹이 비어 있습니다: {target['variable']} in {target['target_values']}"
        )
    log(f"대상 그룹 {len(subset):,}행 (전체 {len(merged):,}행)")
    return merged, subset


# =========================
# 3. 표본 수 공식
# =========================
def _z(alpha: float, power: float) -> Tuple[float, float]:
    """양측 검정의 z_{1-alpha/2}와 z_{1-beta}를 반환한다."""
    return float(stats.norm.ppf(1 - alpha / 2)), float(stats.norm.ppf(power))


def sample_size_continuous(sd: float, mde: float, alpha: float, power: float) -> float:
    """
    연속형 지표의 arm당 필요 표본 수.

        n = 2 (z_{1-alpha/2} + z_{1-beta})^2 * sd^2 / delta^2

    Args:
        sd: 지표의 표준편차
        mde: 탐지하려는 최소 효과 크기 (지표와 같은 단위)
        alpha: 유의수준 (양측)
        power: 검정력

    Returns:
        float: arm당 필요 표본 수
    """
    z_a, z_b = _z(alpha, power)
    return 2 * (z_a + z_b) ** 2 * sd**2 / mde**2


def sample_size_proportion(p1: float, delta: float, alpha: float, power: float) -> float:
    """
    비율형 지표의 arm당 필요 표본 수.

        n = (z_{1-alpha/2} + z_{1-beta})^2 * [p1(1-p1) + p2(1-p2)] / delta^2

    Args:
        p1: 기준 비율 (예: 0.136)
        delta: 탐지하려는 절대 감소폭 (예: 0.01 = 1%p)
        alpha: 유의수준 (양측)
        power: 검정력

    Returns:
        float: arm당 필요 표본 수

    Raises:
        ValueError: delta가 p1보다 커서 목표 비율이 음수가 되는 경우
    """
    if delta >= p1:
        raise ValueError(f"MDE({delta})가 baseline 비율({p1})보다 커서 목표값이 음수가 됩니다.")
    z_a, z_b = _z(alpha, power)
    p2 = p1 - delta
    return (z_a + z_b) ** 2 * (p1 * (1 - p1) + p2 * (1 - p2)) / delta**2


# =========================
# 4. 클러스터 랜덤화 비용 (ICC / Design Effect)
# =========================
def icc_and_design_effect(df: pd.DataFrame, cluster_col: str, value_col: str = "_metric_days") -> Dict[str, Any] | None:
    """
    클러스터 단위로 랜덤화할 때의 ICC와 Design Effect를 계산한다.

    같은 클러스터(같은 셀러, 같은 우편번호 권역)에 속한 주문들은 서로 닮아
    있어 독립 관측치가 아니다. ICC는 그 닮은 정도이고, Design Effect는
    필요 표본 수에 곱해야 할 배수다.

        DE = 1 + (평균 클러스터 크기 - 1) * ICC

    ICC가 0이면 DE=1(손해 없음), ICC가 1이면 DE=클러스터 크기
    (클러스터 하나가 관측치 하나 값어치).

    Args:
        df: 대상 그룹 DataFrame
        cluster_col: 클러스터를 식별하는 컬럼
        value_col: 지표 컬럼

    Returns:
        Dict[str, Any] | None: n_clusters, avg_cluster_size, icc, design_effect.
        컬럼이 없거나 클러스터가 2개 미만이면 None.
    """
    if cluster_col not in df.columns:
        return None
    clean = df[[cluster_col, value_col]].dropna()
    grouped = clean.groupby(cluster_col)[value_col]
    sizes, means = grouped.size(), grouped.mean()
    n, n_clusters = len(clean), len(sizes)
    if n_clusters < 2 or n == n_clusters:
        return None

    grand_mean = clean[value_col].mean()
    ms_between = (sizes * (means - grand_mean) ** 2).sum() / (n_clusters - 1)
    ms_within = ((clean[value_col] - clean[cluster_col].map(means)) ** 2).sum() / (n - n_clusters)
    # 클러스터 크기가 불균등할 때의 보정 계수
    m0 = (n - (sizes**2).sum() / n) / (n_clusters - 1)
    icc = float((ms_between - ms_within) / (ms_between + (m0 - 1) * ms_within))
    avg_size = float(sizes.mean())

    return {
        "unit": cluster_col,
        "n_clusters": int(n_clusters),
        "avg_cluster_size": round(avg_size, 1),
        "icc": round(icc, 4),
        "design_effect": round(1 + (avg_size - 1) * icc, 2),
    }


# =========================
# 5. 가드레일 기준선
# =========================
def guardrail_baselines(
    subset: pd.DataFrame, selected: List[str], definitions: Dict[str, Any],
    data_dir: str, order_key: str,
) -> List[Dict[str, Any]]:
    """
    사람이 선택한 가드레일 지표의 기준선을 계산한다.

    정의에 없는 이름이나 원본 파일에 없는 컬럼은 조용히 넘기지 않고
    status를 붙여 산출물에 남긴다. "측정할 수 없는 것을 가드레일로
    적어두는 것"을 막기 위해서다.

    Args:
        subset: 대상 그룹 주문
        selected: experiment_approval.yaml의 guardrail_metrics 목록
        definitions: experiment_policy.guardrail_metrics
        data_dir: raw CSV 폴더
        order_key: 분석 단위를 식별하는 컬럼 (experiment_policy.order_key)

    Returns:
        List[Dict[str, Any]]: 지표별 기준선 또는 not_evaluable 사유
    """
    results = []
    for name in selected:
        spec = definitions.get(name)
        if spec is None:
            results.append({"metric": name, "status": "not_evaluable",
                            "reason": "experiment_policy.guardrail_metrics에 정의가 없습니다."})
            continue

        path = Path(data_dir) / spec["file"]
        if not path.exists():
            results.append({"metric": name, "status": "not_evaluable",
                            "reason": f"원본 파일이 없습니다: {spec['file']}"})
            continue

        raw = pd.read_csv(path)
        series = raw.groupby(order_key)[spec["column"]].agg(spec.get("agg", "mean"))
        joined = subset.join(series, on=order_key)[spec["column"]].dropna()
        results.append({
            "metric": name,
            "label": spec.get("label", name),
            "status": "ok",
            "mean": round(float(joined.mean()), 3),
            "sd": round(float(joined.std()), 3),
            "n": int(len(joined)),
            "unit": spec.get("unit"),
        })
    return results


# =========================
# 6. 실행 가능성 판정
# =========================
def build_metric_option(
    metric_type: str, label: str, unit: str, mde: float, baseline_value: float,
    n_per_arm: float, daily_orders: float, max_duration_days: int,
) -> Dict[str, Any]:
    """
    지표 하나에 대한 표본 수/기간/실행가능성을 한 덩어리로 만든다.

    Args:
        metric_type: "continuous" 또는 "proportion"
        label: 지표 이름
        unit: MDE 단위 표기
        mde: 최소 탐지 효과
        baseline_value: 기준값 (상대 개선폭 계산용)
        n_per_arm: arm당 필요 표본 수
        daily_orders: 하루 유입 주문 수
        max_duration_days: 실행 가능 임계 기간

    Returns:
        Dict[str, Any]: 지표 옵션 한 건
    """
    # arm당 표본을 먼저 반올림한 뒤 총계를 산출한다. 총계를 따로 반올림하면
    # per_group * 2와 1건씩 어긋나 보고서 안에서 숫자가 맞지 않는다.
    per_group = int(round(n_per_arm))
    total = 2 * per_group
    duration = total / daily_orders
    return {
        "metric_type": metric_type,
        "metric": label,
        "mde": round(mde, 4),
        "mde_unit": unit,
        "relative_pct": round(mde / baseline_value * 100, 1),
        "sample_size_per_group": per_group,
        "sample_size_total": total,
        "estimated_duration_days": int(round(duration)),
        "feasible": bool(duration <= max_duration_days),
    }


def assess_feasibility(
    selected: Dict[str, Any], alternatives: List[Dict[str, Any]], max_duration_days: int
) -> Dict[str, Any]:
    """
    선택된 설계가 실행 가능한지 판정하고, 불가능하면 대안을 제시한다.

    Args:
        selected: 사람이 고른 설계의 계산 결과
        alternatives: 비교용으로 계산해둔 다른 옵션들
        max_duration_days: 실행 가능 임계 기간

    Returns:
        Dict[str, Any]: status, message, feasible_alternatives
    """
    if selected["feasible"]:
        return {
            "status": "feasible",
            "max_duration_days": max_duration_days,
            "message": (
                f"예상 기간 {selected['estimated_duration_days']}일로 "
                f"임계값 {max_duration_days}일 이내이다."
            ),
            "feasible_alternatives": [],
        }

    # 대안의 우선순위는 "기간이 짧은 순"이 아니라 "목표를 유지하는 순"이다.
    # 지표 유형 변경(metric_change)은 같은 상대 개선폭을 유지한 채 측정
    # 방식만 바꾸는 것이고, MDE 완화(mde_relaxation)는 탐지하려는 효과 자체를
    # 키우는 것이다. 후자가 기간이 더 짧게 나오더라도 먼저 권하면
    # "목표를 낮춰 표본을 줄였다"는 비판을 자초하므로 뒤로 미룬다.
    feasible = sorted(
        (a for a in alternatives if a["feasible"]),
        key=lambda a: (a.get("kind") == "mde_relaxation", a["estimated_duration_days"]),
    )
    if feasible:
        best = feasible[0]
        how = (
            "1차 지표를 바꾸면" if best.get("kind") == "metric_change"
            else f"MDE를 {best['mde']}{best['mde_unit']}로 완화하면"
        )
        message = (
            f"예상 기간 {selected['estimated_duration_days']}일로 임계값 "
            f"{max_duration_days}일을 초과한다. 대안: {how} "
            f"{best['metric']} 기준 {best['estimated_duration_days']}일에 판단이 가능하다"
            f"(상대 개선폭 {best['relative_pct']}%)."
        )
    else:
        message = (
            f"예상 기간 {selected['estimated_duration_days']}일로 임계값 "
            f"{max_duration_days}일을 초과하며, 계산한 대안 중 임계값을 "
            f"만족하는 것이 없다. 대상 모집단 확대나 실험 범위 재정의가 필요하다."
        )
    return {
        "status": "infeasible",
        "max_duration_days": max_duration_days,
        "message": message,
        "feasible_alternatives": feasible,
    }


# =========================
# 7. 전체 실행 함수
# =========================
def run(
    config_dir: str = CONFIG_DIR,
    data_dir: str = DATA_DIR,
    output_dir: str = OUTPUT_DIR,
) -> Dict[str, Any]:
    """
    ⑦ Experiment Design 전체 실행.

    experiment_approval.yaml(사람의 판단) + 분석 산출물을 읽어
    experiment_design_report.json을 생성한다.

    Args:
        config_dir: experiment_approval.yaml, kpi_definition.yaml이 있는 폴더
        data_dir: raw CSV 폴더
        output_dir: 분석 산출물이 있고 결과를 저장할 폴더

    Returns:
        Dict[str, Any]: 생성된 리포트 (경로는 "report_path" 키)
    """
    output_dir = ensure_dir(output_dir)

    approval = load_yaml(str(Path(config_dir) / "experiment_approval.yaml"))
    kpi_config = load_yaml(str(Path(config_dir) / "kpi_definition.yaml"))
    approved_features_all = load_yaml(str(Path(config_dir) / "approved_features.yaml"))
    policy = kpi_config["experiment_policy"]

    recommended = load_json(str(Path(output_dir) / "recommended_scenario.json"))
    simulation_report = load_json(str(Path(output_dir) / "simulation_report.json"))
    effect_size_report = load_json(str(Path(output_dir) / "effect_size_report.json"))
    data_dictionary = load_json(str(Path(output_dir) / "data_dictionary.json"))
    processed_df = pd.read_parquet(Path(output_dir) / "processed_dataset.parquet")

    alpha, power = policy["alpha"], policy["power"]
    max_days = policy["max_duration_days"]

    target = resolve_target(
        approval, recommended, simulation_report, effect_size_report, kpi_config
    )
    full_df, subset = build_target_dataset(
        target, processed_df, data_dictionary, approved_features_all, policy, data_dir
    )

    # --- baseline ---
    # 데이터셋 종속 컬럼명은 전부 kpi_definition.yaml에서 읽는다.
    delay_metric = kpi_config["delay_metric"]
    unit = policy["kpi_display_unit"]
    metric_days = subset["_metric_days"]
    delay_rate = float((subset[delay_metric["kpi_column"]] > 0).mean())
    purchase = pd.to_datetime(subset[policy["traffic_timestamp"]])
    period_days = int((purchase.max() - purchase.min()).days)
    daily_orders = len(subset) / period_days

    baseline = {
        "target_variable": target["variable"],
        "target_values": target["target_values"],
        "order_count": int(len(subset)),
        "metric_mean": round(float(metric_days.mean()), 2),
        "metric_sd": round(float(metric_days.std()), 2),
        "metric_unit": unit,
        "delay_rate_pct": round(delay_rate * 100, 2),
        "overall_metric_mean": round(float(full_df["_metric_days"].mean()), 2),
        "observation_period_days": period_days,
        "estimated_daily_orders": round(daily_orders, 1),
    }

    # --- 지표 유형별 비교 ---
    # 사람이 고른 MDE를 상대 개선폭(%)으로 환산한 뒤, 같은 상대 폭을 다른
    # 지표 유형에도 적용한다. 그래야 "목표를 낮춰서 표본을 줄인 것 아니냐"는
    # 반문에 숫자로 답할 수 있다.
    mde_value = float(approval["mde"]["value"])
    primary_type = approval["primary_metric_type"]
    sd_days, mean_days = float(metric_days.std()), float(metric_days.mean())

    relative = mde_value / (mean_days if primary_type == "continuous" else delay_rate)
    cont_mde = mde_value if primary_type == "continuous" else relative * mean_days
    prop_mde = mde_value if primary_type == "proportion" else relative * delay_rate

    options = [
        build_metric_option(
            "continuous", f"{target['metric_label']} ({unit})", unit, cont_mde, mean_days,
            sample_size_continuous(sd_days, cont_mde, alpha, power), daily_orders, max_days,
        ),
        build_metric_option(
            "proportion", f"{delay_metric.get('name', delay_metric['kpi_column'])} Rate (%)",
            "%p", prop_mde, delay_rate,
            sample_size_proportion(delay_rate, prop_mde, alpha, power), daily_orders, max_days,
        ),
    ]
    selected_option = next(o for o in options if o["metric_type"] == primary_type)

    # --- 랜덤화 단위별 비용 ---
    n_base = selected_option["sample_size_per_group"]
    units: List[Dict[str, Any]] = [{
        "unit": "order", "n_clusters": None, "avg_cluster_size": None, "icc": None,
        "design_effect": 1.0, "sample_size_per_group": n_base,
        "estimated_duration_days": int(round(2 * n_base / daily_orders)),
        "status": "ok",
    }]
    for cand in policy.get("randomization_unit_candidates", []):
        col = cand.get("column", cand["name"])
        result = icc_and_design_effect(subset, col)
        if result is None:
            units.append({"unit": cand["name"], "status": "not_evaluable",
                          "reason": f"'{col}' 컬럼이 없거나 클러스터를 구성할 수 없습니다."})
            continue
        n_arm = n_base * result["design_effect"]
        result.update({
            "unit": cand["name"], "status": "ok",
            "sample_size_per_group": int(round(n_arm)),
            "estimated_duration_days": int(round(2 * n_arm / daily_orders)),
        })
        units.append(result)
    for spec in policy.get("not_evaluable_units", []):
        units.append({"unit": spec["name"], "status": "not_evaluable",
                      "reason": str(spec["reason"]).strip()})

    chosen_unit = approval["experiment_unit"]
    unit_entry = next((u for u in units if u["unit"] == chosen_unit), None)
    if unit_entry is None or unit_entry.get("status") != "ok":
        raise ValueError(
            f"승인된 실험 단위 '{chosen_unit}'을 이 데이터셋에서 평가할 수 없습니다. "
            f"평가 가능한 단위: {[u['unit'] for u in units if u.get('status') == 'ok']}"
        )

    # 선택된 단위의 Design Effect를 반영한 최종 설계
    design_effect = unit_entry["design_effect"]
    final_per_group = unit_entry["sample_size_per_group"]
    final_total = 2 * final_per_group
    final_duration = int(round(final_total / daily_orders))
    final = {
        **selected_option,
        "experiment_unit": chosen_unit,
        "design_effect": design_effect,
        "sample_size_per_group": final_per_group,
        "sample_size_total": final_total,
        "estimated_duration_days": final_duration,
        "feasible": final_duration <= max_days,
    }

    # --- 실행 가능성 판정 (불가능하면 MDE 상향안까지 계산) ---
    alternatives = [
        {**o, "kind": "metric_change"} for o in options if o["metric_type"] != primary_type
    ]
    if not final["feasible"]:
        for factor in policy.get("mde_relaxation_factors", []):
            relaxed = cont_mde * factor if primary_type == "continuous" else prop_mde * factor
            n_arm = (
                sample_size_continuous(sd_days, relaxed, alpha, power)
                if primary_type == "continuous"
                else sample_size_proportion(delay_rate, relaxed, alpha, power)
            ) * design_effect
            alternatives.append({
                **build_metric_option(
                    primary_type, f"{selected_option['metric']} (MDE x{factor})",
                    selected_option["mde_unit"], relaxed,
                    mean_days if primary_type == "continuous" else delay_rate,
                    n_arm, daily_orders, max_days,
                ),
                "kind": "mde_relaxation",
            })
    feasibility = assess_feasibility(final, alternatives, max_days)

    report = {
        "scenario": target,
        "baseline": baseline,
        "power_analysis": {
            "alpha": alpha,
            "sided": "two-sided",
            "power": power,
            "formula_continuous": "n_per_arm = 2 * (z_(1-alpha/2) + z_(1-beta))^2 * sd^2 / delta^2",
            "formula_proportion": "n_per_arm = (z_(1-alpha/2) + z_(1-beta))^2 * [p1(1-p1) + p2(1-p2)] / delta^2",
            "design_effect_formula": "DE = 1 + (avg_cluster_size - 1) * ICC",
        },
        "metric_options": options,
        "randomization_units": units,
        "selected_design": final,
        "feasibility": feasibility,
        "guardrail_baselines": guardrail_baselines(
            subset, approval.get("guardrail_metrics", []),
            policy.get("guardrail_metrics", {}), data_dir, policy["order_key"],
        ),
    }

    report_path = Path(output_dir) / "experiment_design_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f"experiment_design_report.json 저장 완료: {report_path}")
    log(f"실행 가능성: {feasibility['status']} — {feasibility['message']}")

    report["report_path"] = str(report_path)
    return report
