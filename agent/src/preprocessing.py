# preprocessing.py
"""
② 전처리 모듈
- kpi_definition.yaml에 지정된 base_table_file 하나만 로드해서 정제
  (다른 테이블과의 조인은 이 단계에서 하지 않음)
- kpi_definition.yaml에 정의된 프로세스 구간(start/end 컬럼)으로 KPI 컬럼 생성
- kpi_definition.yaml에 정의된 delay_metric으로 지연 지표 생성
- preprocessing_policy.yaml에 정의된 정책(필터링, 음수/결측치 제거)을 그대로 실행
- Agent(Python Tool)는 정책을 "판단"하지 않고 "실행"만 한다

Assumption: processed_dataset.parquet은 base_table의 row 단위(grain)를 유지한다.
다른 테이블과의 조인은 여기서 하지 않고, 필요한 시점(예: root_cause_analysis.py)에
join_engine.build_analysis_dataset()을 호출해 그때그때 선택적으로 조인한다.

base_table_file만 지정하면 base_table(테이블명)은 stem으로 자동 도출한다.
data_understanding.py가 테이블명을 파일명 그대로(stem) 사용하므로,
이렇게 해야 두 모듈에서 만들어지는 테이블명이 항상 일치하고
join_engine을 통한 조인 시 이름 불일치 문제가 생기지 않는다.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
import pandas as pd
import yaml
from config import DATA_DIR, CONFIG_DIR, OUTPUT_DIR, ensure_dir, log


# =========================
# 1. 설정 로드
# =========================
def load_yaml(path: str) -> Dict[str, Any]:
    """
    YAML 설정 파일 로드

    Args:
        path: yaml 파일 경로

    Returns:
        Dict[str, Any]: 파싱된 설정
    """
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_base_table_name(kpi_config: Dict[str, Any]) -> str:
    """
    kpi_definition.yaml의 base_table_file로부터 테이블명을 자동 도출.
    data_understanding.py가 테이블명을 파일명 그대로(확장자 제외) 쓰는 것과
    항상 일치시키기 위해, base_table을 별도로 적지 않고 여기서 유도한다.

    Args:
        kpi_config: kpi_definition.yaml 파싱 결과 (base_table_file 키 필요)

    Returns:
        str: 테이블명 (예: "olist_orders_dataset.csv" → "olist_orders_dataset")
    """
    return Path(kpi_config["base_table_file"]).stem


# =========================
# 2. base_table 로드
# =========================
def load_base_table(data_dir: str, kpi_config: Dict[str, Any]) -> pd.DataFrame:
    """
    kpi_definition.yaml에 지정된 base_table_file만 로드.
    파일명을 하드코딩하지 않고 설정에서 받아, 데이터셋이 바뀌어도
    이 파일을 고치지 않고 kpi_definition.yaml만 수정하면 동작한다.

    Args:
        data_dir: raw CSV 폴더 경로
        kpi_config: kpi_definition.yaml 파싱 결과 (base_table_file 키 필요)

    Returns:
        pd.DataFrame: base_table 원본

    Raises:
        KeyError: kpi_config에 base_table_file이 없는 경우
        FileNotFoundError: 지정된 파일이 존재하지 않는 경우
    """
    filename = kpi_config["base_table_file"]
    path = Path(data_dir) / filename
    if not path.exists():
        raise FileNotFoundError(f"{path}를 찾을 수 없습니다.")
    df = pd.read_csv(path)
    log(f"{filename} 로드 완료: {len(df)}행")
    return df


# =========================
# 3. KPI 컬럼 생성 (kpi_definition.yaml 기반)
# =========================
def convert_datetime_columns(df: pd.DataFrame, kpi_config: Dict[str, Any]) -> pd.DataFrame:
    """
    kpi_definition.yaml의 processes와 delay_metric에 등장하는
    컬럼들을 datetime 타입으로 변환

    Args:
        df: 대상 DataFrame
        kpi_config: kpi_definition.yaml 파싱 결과

    Returns:
        pd.DataFrame: datetime 변환이 적용된 DataFrame
    """
    datetime_cols = set()
    for process in kpi_config.get("processes", []):
        datetime_cols.add(process["start"])
        datetime_cols.add(process["end"])

    delay_metric = kpi_config.get("delay_metric")
    if delay_metric:
        datetime_cols.add(delay_metric["actual"])
        datetime_cols.add(delay_metric["estimated"])

    df = df.copy()
    for col in datetime_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    log(f"datetime 변환 완료: {sorted(datetime_cols)}")
    return df


def calculate_kpi_columns(df: pd.DataFrame, kpi_config: Dict[str, Any]) -> pd.DataFrame:
    """
    kpi_definition.yaml에 정의된 프로세스 구간별 소요시간(hours) KPI 컬럼 생성

    Args:
        df: 대상 DataFrame (datetime 변환 완료된 상태)
        kpi_config: kpi_definition.yaml 파싱 결과
            예: {"processes": [{"name": "Seller Processing",
                                 "start": "order_approved_at",
                                 "end": "order_delivered_carrier_date"}, ...]}

    Returns:
        pd.DataFrame: KPI 컬럼(snake_case, _time 접미사)이 추가된 DataFrame
    """
    df = df.copy()
    for process in kpi_config.get("processes", []):
        kpi_col = process.get("kpi_column") or (
            process["name"].lower().replace(" ", "_") + "_time"
        )
        start_col, end_col = process["start"], process["end"]
        if start_col in df.columns and end_col in df.columns:
            df[kpi_col] = (df[end_col] - df[start_col]).dt.total_seconds() / 3600
            log(f"KPI 생성: {kpi_col} = ({end_col} - {start_col}) in hours")
        else:
            log(f"KPI 생성 실패(컬럼 없음): {kpi_col} ({start_col}, {end_col})")
    return df


def calculate_delay_metric(df: pd.DataFrame, kpi_config: Dict[str, Any]) -> pd.DataFrame:
    """
    kpi_definition.yaml의 delay_metric에 정의된 대로 지연 지표를 계산.
    processes(구간 소요시간)와 계산 방식이 다르므로 별도 함수로 분리.
    (실제 - 예상, 양수 = 지연)

    Args:
        df: 대상 DataFrame (datetime 변환 완료된 상태)
        kpi_config: kpi_definition.yaml 파싱 결과
            예: {"delay_metric": {"actual": "order_delivered_customer_date",
                                    "estimated": "order_estimated_delivery_date",
                                    "kpi_column": "delivery_delay"}}

    Returns:
        pd.DataFrame: delay 컬럼이 추가된 DataFrame (delay_metric 없으면 그대로 반환)
    """
    delay_metric = kpi_config.get("delay_metric")
    if not delay_metric:
        return df

    df = df.copy()
    actual_col, estimated_col = delay_metric["actual"], delay_metric["estimated"]
    kpi_col = delay_metric.get("kpi_column", "delay")

    if actual_col in df.columns and estimated_col in df.columns:
        df[kpi_col] = (df[actual_col] - df[estimated_col]).dt.total_seconds() / 3600
        log(f"지연 지표 생성: {kpi_col} = ({actual_col} - {estimated_col}) in hours")
    else:
        log(f"지연 지표 생성 실패(컬럼 없음): {kpi_col} ({actual_col}, {estimated_col})")
    return df


# =========================
# 4. 전처리 정책 실행 (preprocessing_policy.yaml 기반)
# =========================
def apply_preprocessing_policy(df: pd.DataFrame, policy: Dict[str, Any]) -> pd.DataFrame:
    """
    preprocessing_policy.yaml에 정의된 정책을 순서대로 실행.
    Agent는 정책의 타당성을 판단하지 않고 정의된 대로 실행만 한다.

    지원 정책 키:
    - filters: {컬럼명: 값} 형태로 등호 필터링 (예: order_status: delivered)
    - drop_negative: 음수면 제거할 컬럼 목록
    - drop_na_columns: 결측치 있으면 행을 제거할 컬럼 목록
    - keep_outliers: True면 극단값을 제거하지 않고 유지 (기본 True)

    Args:
        df: 대상 DataFrame
        policy: preprocessing_policy.yaml 파싱 결과

    Returns:
        pd.DataFrame: 정책이 적용된 DataFrame
    """
    df = df.copy()
    before = len(df)

    for col, value in policy.get("filters", {}).items():
        if col in df.columns:
            df = df[df[col] == value]
            log(f"필터 적용: {col} == {value} → {len(df)}행 남음")

    for col in policy.get("drop_negative", []):
        if col in df.columns:
            removed = (df[col] < 0).sum()
            df = df[~(df[col] < 0)]
            log(f"음수값 제거: {col} ({removed}건 제거) → {len(df)}행 남음")

    na_cols = [c for c in policy.get("drop_na_columns", []) if c in df.columns]
    if na_cols:
        before_na = len(df)
        df = df.dropna(subset=na_cols)
        log(f"결측치 제거: {na_cols} ({before_na - len(df)}건 제거) → {len(df)}행 남음")

    if not policy.get("keep_outliers", True):
        log("keep_outliers=False 설정이지만 별도 극단값 제거 로직은 정의되어 있지 않습니다.")

    log(f"전처리 정책 실행 완료: {before}행 → {len(df)}행")
    return df


# =========================
# 5. 전체 실행 함수
# =========================
def run(
    data_dir: str = DATA_DIR,
    config_dir: str = CONFIG_DIR,
    output_dir: str = OUTPUT_DIR,
) -> Dict[str, str]:
    """
    ② 전처리 단계 전체 실행:
    base_table_file 로드 → datetime 변환 → KPI 계산 → 지연 지표 계산 → 정책 적용
    → processed_dataset.parquet 저장 (base_table의 grain 유지)

    Args:
        data_dir: raw CSV 폴더 경로
        config_dir: kpi_definition.yaml, preprocessing_policy.yaml이 있는 폴더
        output_dir: 결과물을 저장할 폴더

    Returns:
        Dict[str, str]: 생성된 파일 경로
    """
    output_dir = ensure_dir(output_dir)

    kpi_config = load_yaml(str(Path(config_dir) / "kpi_definition.yaml"))
    policy = load_yaml(str(Path(config_dir) / "preprocessing_policy.yaml"))

    base_table_name = get_base_table_name(kpi_config)
    log(f"base_table: {base_table_name}")

    df = load_base_table(data_dir, kpi_config)
    df = convert_datetime_columns(df, kpi_config)
    df = calculate_kpi_columns(df, kpi_config)
    df = calculate_delay_metric(df, kpi_config)
    df = apply_preprocessing_policy(df, policy)

    output_path = Path(output_dir) / "processed_dataset.parquet"
    df.to_parquet(output_path, index=False)
    log(f"processed_dataset.parquet 저장 완료: {len(df)}행, {len(df.columns)}컬럼")

    return {"processed_dataset": str(output_path)}