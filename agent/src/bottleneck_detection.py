# bottleneck_detection.py
"""
③ 병목 탐지 모듈
- processed_dataset.parquet + kpi_definition.yaml만 가지고 계산
- LLM 호출 없음 (순수 Python/pandas 계산)
- 구간별 평균 소요시간, Lead Time 비중, 지연 vs 정상 비교, 전체 지연율 산출
- kpi_definition.yaml의 bottleneck_policy 기준으로 병목 구간을 규칙 기반 판정

Agent는 병목 탐지를 규칙 기반(rule-based)으로 수행한다.
(AI가 판단하는 것이 아니라 이미 정해진 공식대로 계산만 하는 단계)
병목이 "몇 등인지"가 아니라 "정책 기준을 충족하는지"로 판정하기 때문에,
stage가 몇 개든 실제로 병목인 구간만 골라낸다.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd
import matplotlib.pyplot as plt
from config import CONFIG_DIR, OUTPUT_DIR, ensure_dir, log


# =========================
# 1. 설정 로드 & 구간(stage) / 합계(total) 구분
# =========================
def load_yaml(path: str) -> Dict[str, Any]:
    """
    YAML 설정 파일 로드

    Args:
        path: yaml 파일 경로

    Returns:
        Dict[str, Any]: 파싱된 설정
    """
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def split_stages_and_total(kpi_config: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    kpi_definition.yaml의 processes를 "구간(stage)"과 "전체 합계(total)"로 분리.
    is_total: true로 표시된 process는 Lead Time 비중 계산의 분모로만 쓰이고,
    구간 목록에는 포함되지 않는다. (자기 자신을 나누는 의미 없는 100% 항목을 방지)

    Args:
        kpi_config: kpi_definition.yaml 파싱 결과

    Returns:
        tuple: (stage 목록, total process 딕셔너리)

    Raises:
        ValueError: is_total: true인 process가 없거나 2개 이상인 경우
    """
    processes = kpi_config.get("processes", [])
    stages = [p for p in processes if not p.get("is_total", False)]
    totals = [p for p in processes if p.get("is_total", False)]

    if len(totals) != 1:
        raise ValueError(
            f"kpi_definition.yaml의 processes 중 is_total: true는 정확히 1개여야 합니다. "
            f"(현재 {len(totals)}개)"
        )
    return stages, totals[0]


# =========================
# 2. 구간별 평균 소요시간 + Lead Time 비중
# =========================
def calculate_stage_summary(df: pd.DataFrame, stages: List[Dict[str, Any]], total_process: Dict[str, Any]) -> pd.DataFrame:
    """
    구간별 평균 소요시간과 전체 Lead Time 대비 비중을 계산

    Args:
        df: processed_dataset (KPI 컬럼 포함)
        stages: split_stages_and_total()의 stage 목록
        total_process: split_stages_and_total()의 total process

    Returns:
        pd.DataFrame: columns = [stage, avg_hours, share_pct]
    """
    total_col = total_process["kpi_column"]
    total_mean = df[total_col].mean()

    rows = []
    for stage in stages:
        col = stage["kpi_column"]
        avg_hours = df[col].mean()
        rows.append({
            "stage": stage["kpi_column"],
            "stage_name": stage["name"],
            "avg_hours": round(float(avg_hours), 2),
            "share_pct": round(float(avg_hours / total_mean * 100), 2),
        })
    summary = pd.DataFrame(rows).sort_values("share_pct", ascending=False).reset_index(drop=True)
    log(f"구간별 평균/비중 계산 완료: {summary['stage'].tolist()}")
    return summary


# =========================
# 3. 지연 vs 정상 비교
# =========================
def calculate_delayed_vs_normal(df: pd.DataFrame, stages: List[Dict[str, Any]], delay_col: str) -> pd.DataFrame:
    """
    지연 주문(delay_col > 0)과 정상 주문의 구간별 평균 소요시간을 비교

    Args:
        df: processed_dataset
        stages: split_stages_and_total()의 stage 목록
        delay_col: 지연 여부 판단 컬럼 (delivery_delay, 양수면 지연)

    Returns:
        pd.DataFrame: columns = [stage, delayed_avg_hours, normal_avg_hours, ratio]
    """
    delayed = df[df[delay_col] > 0]
    normal = df[df[delay_col] <= 0]

    rows = []
    for stage in stages:
        col = stage["kpi_column"]
        delayed_avg = delayed[col].mean()
        normal_avg = normal[col].mean()
        ratio = delayed_avg / normal_avg if normal_avg else None
        rows.append({
            "stage": stage["kpi_column"],
            "stage_name": stage["name"],
            "delayed_avg_hours": round(float(delayed_avg), 2),
            "normal_avg_hours": round(float(normal_avg), 2),
            "ratio": round(float(ratio), 2) if ratio is not None else None,
        })
    result = pd.DataFrame(rows)
    log(f"지연 vs 정상 비교 완료: 지연 {len(delayed)}건 / 정상 {len(normal)}건")
    return result


# =========================
# 4. 전체 지연율
# =========================
def calculate_delay_rate(df: pd.DataFrame, delay_col: str) -> float:
    """
    전체 주문 중 지연 주문의 비율(%) 계산

    Args:
        df: processed_dataset
        delay_col: 지연 여부 판단 컬럼 (양수면 지연)

    Returns:
        float: 지연율(%)
    """
    rate = (df[delay_col] > 0).mean() * 100
    return round(float(rate), 2)


# =========================
# 5. 병목 판정 (규칙 기반)
# =========================
def identify_bottlenecks(
    stage_summary: pd.DataFrame,
    comparison: pd.DataFrame,
    policy: Dict[str, Any],
) -> List[str]:
    """
    규칙 기반으로 병목 구간을 판정한다.
    두 지표(비중, 지연 배율)를 모두 충족해야 병목으로 인정한다 (AND 조건).

    이렇게 두 지표를 함께 보는 이유는, 비중이 크더라도 지연 시 배율이
    거의 벌어지지 않으면 "원래 오래 걸리는 구간일 뿐 지연의 원인은
    아닐 수 있다"는 판단이 가능하기 때문이다. 노트북 분석에서
    payment_approval(share 3.2%, ratio 1.28배)이 둘 다 낮아 병목에서
    제외되고, seller_processing/carrier_delivery는 둘 다 기준을 크게
    넘어서 병목으로 판정된 패턴을 그대로 규칙화한 것.

    이전 버전은 "무조건 상위 1~2개"를 병목으로 지정했는데, 이는
    stage 개수에 따라 진짜 병목이 아닌 구간도 포함되거나, 진짜 병목이
    누락될 수 있는 문제가 있었다. 이 함수는 정책 기준을 충족하는
    구간만 골라내므로 stage 개수와 무관하게 항상 정확하다.

    Args:
        stage_summary: calculate_stage_summary()의 결과 (share_pct 포함)
        comparison: calculate_delayed_vs_normal()의 결과 (ratio 포함)
        policy: kpi_definition.yaml의 bottleneck_policy
            {"min_share_pct": 15, "min_delay_ratio": 1.5}

    Returns:
        List[str]: 병목으로 판정된 stage_name 목록 (share_pct 내림차순)
    """
    min_share = policy.get("min_share_pct", 0)
    min_ratio = policy.get("min_delay_ratio", 0)

    merged = stage_summary.merge(
        comparison[["stage", "ratio"]], on="stage", how="left"
    )

    bottlenecks = merged[
        (merged["share_pct"] >= min_share) & (merged["ratio"] >= min_ratio)
    ].sort_values("share_pct", ascending=False)

    result = bottlenecks["stage_name"].tolist()
    log(f"병목 판정 완료: {result} (기준: share>={min_share}%, ratio>={min_ratio})")
    return result


# =========================
# 6. 시각화
# =========================
def plot_stage_time_chart(stage_summary: pd.DataFrame, output_path: str) -> None:
    """
    구간별 평균 소요시간 bar chart 생성

    Args:
        stage_summary: calculate_stage_summary()의 결과
        output_path: 저장할 png 경로
    """
    plt.figure(figsize=(8, 5))
    plt.bar(stage_summary["stage_name"], stage_summary["avg_hours"])
    plt.xlabel("Stage")
    plt.ylabel("Average Hours")
    plt.title("Bottleneck Detection - Average Time per Stage")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    log(f"stage_time_chart 저장 완료: {output_path}")


def plot_delayed_vs_normal(comparison: pd.DataFrame, output_path: str) -> None:
    """
    지연 주문 vs 정상 주문의 구간별 평균 소요시간 비교 bar chart 생성

    Args:
        comparison: calculate_delayed_vs_normal()의 결과
        output_path: 저장할 png 경로
    """
    x = range(len(comparison))
    width = 0.35

    plt.figure(figsize=(8, 5))
    plt.bar([i - width / 2 for i in x], comparison["delayed_avg_hours"], width, label="Delayed")
    plt.bar([i + width / 2 for i in x], comparison["normal_avg_hours"], width, label="Normal")
    plt.xticks(list(x), comparison["stage_name"])
    plt.ylabel("Average Hours")
    plt.title("Delayed vs Normal - Average Time per Stage")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    log(f"delayed_vs_normal 저장 완료: {output_path}")


# =========================
# 7. 전체 실행 함수
# =========================
def run(config_dir: str = CONFIG_DIR, output_dir: str = OUTPUT_DIR) -> Dict[str, str]:
    """
    ③ 병목 탐지 단계 전체 실행:
    processed_dataset.parquet 로드 → 구간별 평균/비중 계산 →
    지연 vs 정상 비교 → 전체 지연율 → 규칙 기반 병목 판정 →
    bottleneck_report.json 저장 → 시각화 2개 생성

    Args:
        config_dir: kpi_definition.yaml이 있는 폴더
        output_dir: processed_dataset.parquet이 있고 결과물을 저장할 폴더

    Returns:
        Dict[str, str]: 생성된 파일 경로들
    """
    output_dir = ensure_dir(output_dir)

    kpi_config = load_yaml(str(Path(config_dir) / "kpi_definition.yaml"))
    stages, total_process = split_stages_and_total(kpi_config)

    dataset_path = Path(output_dir) / "processed_dataset.parquet"
    if not dataset_path.exists():
        raise RuntimeError(f"{dataset_path}가 없습니다. preprocessing.run()을 먼저 실행하세요.")
    df = pd.read_parquet(dataset_path)

    delay_metric = kpi_config.get("delay_metric")
    if not delay_metric:
        raise RuntimeError("kpi_definition.yaml에 delay_metric이 정의되어 있지 않습니다.")
    delay_col = delay_metric["kpi_column"]

    stage_summary = calculate_stage_summary(df, stages, total_process)
    comparison = calculate_delayed_vs_normal(df, stages, delay_col)
    delay_rate = calculate_delay_rate(df, delay_col)

    policy = kpi_config.get("bottleneck_policy", {})
    if not policy:
        raise RuntimeError("kpi_definition.yaml에 bottleneck_policy가 정의되어 있지 않습니다.")
    bottlenecks = identify_bottlenecks(stage_summary, comparison, policy)

    bottleneck_report = {
        "total_orders": int(len(df)),
        "delay_rate_pct": delay_rate,
        "stage_summary": stage_summary.to_dict(orient="records"),
        "delayed_vs_normal": comparison.to_dict(orient="records"),
        "bottleneck_policy": policy,
        "bottlenecks": bottlenecks,
    }

    report_path = Path(output_dir) / "bottleneck_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(bottleneck_report, f, ensure_ascii=False, indent=2)
    log(f"bottleneck_report.json 저장 완료: {report_path}")

    chart_path = Path(output_dir) / "stage_time_chart.png"
    plot_stage_time_chart(stage_summary, str(chart_path))

    compare_path = Path(output_dir) / "delayed_vs_normal.png"
    plot_delayed_vs_normal(comparison, str(compare_path))

    return {
        "bottleneck_report": str(report_path),
        "stage_time_chart": str(chart_path),
        "delayed_vs_normal": str(compare_path),
    }