# root_cause_analysis.py
"""
④ Root Cause Analysis 모듈
- bottleneck_report.json의 각 병목 구간에 대해:
  Step 1: LLM이 후보 feature 제안 (candidate_features_{stage}.md)
  [Human Review]: approved_features.yaml
  Step 2: Python이 η²/r² 계산 (effect_size_report.json)
  Step 3: LLM이 결과 해석 (rootcause_report.json, cause_effect_structure.json)
  Step 4: Python이 graphviz 다이어그램 생성 (cause_effect_diagram_{stage}.png)

역할 분리 원칙: LLM은 "무엇을 분석할지" 판단하고 해석하며,
Python Tool은 실제 통계 계산과 시각화를 담당한다.

Step 1 설계 원칙: LLM에게 병목 구간 이름만 주면, 그 구간과 무관한
timestamp(예: Carrier Delivery인데 order_purchase_timestamp)를 "직접
변수"로 착각해 제안할 수 있다. 이를 방지하기 위해 kpi_definition.yaml에
이미 정의된 해당 stage의 정확한 start/end 컬럼(target_kpi_definition)을
프롬프트에 명시적으로 전달한다. 또한 후보를 Direct(이 KPI의 start/end
시점에서 직접 파생되거나 직접 관여하는 변수)와 Indirect(시점은 다르지만
간접적으로 영향을 줄 수 있는 변수)로 구분해 제안하도록 해서, 유효한
간접 신호(예: 주문 시점의 계절성)를 억지로 배제하지 않으면서도 Human이
검토할 때 어느 쪽이 이 KPI를 더 직접적으로 설명하는지 판단하기 쉽게 한다.

Step 2 설계 원칙: 이 프로젝트는 노트북에서 수행한 기존 분석을 Agent가
재현하는 것이 1순위 목표다. 노트북은 customer_state처럼 orders와 1:1
관계인 변수는 order-level 그대로, seller_state/product_category_name/
product_weight_g처럼 order_items를 경유해야 하는 변수는 그 관계를 그대로
따라 조인 후(행이 늘어난 상태로) η²/r²를 계산했다. 이 방식이 통계적으로
완벽히 엄밀하지 않을 수 있다는 점(order당 item이 여러 개면 같은 KPI 값이
중복 반영됨)을 인지하고 있으나, Olist 데이터에서 order당 다중 seller
비율은 1.30%, 다중 category 비율은 0.74%로 실질적 영향이 미미함을 확인
했다(agent 실행 로그 참고). 따라서 이번 구현은 압축(집계) 없이 노트북과
동일한 방식으로 조인해 계산하며, kpi_definition.yaml의 level 필드에
"이 KPI가 order 단위로 측정된다"는 메타데이터만 남겨, 향후 item-level
KPI를 가진 다른 이커머스 데이터셋에 적용할 경우 aggregation이 필요할 수
있다는 확장 포인트로 문서화해 둔다.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List
import numpy as np
import pandas as pd
import yaml
import matplotlib.pyplot as plt
from scipy import stats
from labels import format_derived_value
from config import CONFIG_DIR, DATA_DIR, OUTPUT_DIR, CHAT_MODEL, ensure_dir, get_anthropic_client, log
from join_engine import build_analysis_dataset


# =========================
# 1. 설정/데이터 로드 유틸
# =========================
def load_json(path: str) -> Dict[str, Any]:
    """
    JSON 파일 로드

    Args:
        path: json 파일 경로

    Returns:
        Dict[str, Any]: 파싱된 내용
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_text(path: str) -> str:
    """
    텍스트(Markdown 등) 파일 로드

    Args:
        path: 파일 경로

    Returns:
        str: 파일 내용
    """
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


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


# =========================
# 2. Step 1: LLM 후보 feature 제안
# =========================
CANDIDATE_FEATURE_SYSTEM_PROMPT = """당신은 이커머스 물류 데이터 분석 전문가입니다.
주어진 KPI 정의, 병목 구간 정보, 데이터 딕셔너리, 스키마 설명을 보고,
이 병목 구간의 소요시간에 영향을 줄 것 같은 변수(feature) 후보를
Markdown 목록으로 제안하세요.

핵심 원칙:
- 입력에 포함된 target_kpi_definition(start/end 컬럼)을 반드시 참고하세요.
  이 KPI는 "start 시점부터 end 시점까지의 소요시간"을 의미합니다.
- 후보는 "직접 관련 변수(Direct Features)"와 "간접 관련 변수(Indirect Features)"
  두 그룹으로 나누어 제안하세요.
  - Direct Features: 이 KPI의 start 또는 end 시점에서 파생된 시간 변수
    (예: start 컬럼의 월/요일), 또는 이 구간에 직접 관여하는 주체(예: 배송
    구간이면 배송 관련 지역/업체 정보)의 컬럼.
  - Indirect Features: 이 KPI와 시점이 다르지만 간접적으로 영향을 줄 수 있는
    변수 (예: 주문 시점의 계절성, 상품 자체의 속성 등).
- order_id, customer_id, seller_id, product_id, review_id 같은
  식별자(고유값) 컬럼은 후보에서 제외하세요.
- payment_value, price처럼 이 병목과 인과관계가 없어 보이는 컬럼도 제외하세요.
- 각 그룹에 3~5개씩, 각 후보마다 "테이블명.컬럼명" 형식과 왜 영향을 줄 것
  같은지 한 줄 이유를 쓰세요.
- 위경도 거리 계산처럼 여러 테이블을 조합해 새로 만들어야 하는 복잡한
  파생 변수는 제안하지 마세요. 이미 존재하는 컬럼이거나, 하나의 timestamp
  컬럼에서 월/요일을 추출하는 정도의 단순한 파생 변수만 제안하세요.
- 출력은 Markdown 형식으로만, 서론/결론 문장 없이 목록만 작성하세요.

출력 형식 예:
## Candidate Features for {stage_name}

### Direct Features
- **orders.order_delivered_carrier_date (month)**: [Direct] 이 KPI의 시작 시점
  자체의 계절성이 소요시간에 직접 영향을 줄 수 있음

### Indirect Features
- **orders.order_purchase_timestamp (month)**: [Indirect] 주문 시점의 계절적
  물량 변동이 이후 처리에 간접적으로 영향을 줄 수 있음
"""

async def suggest_candidate_features(
    stage_name: str,
    bottleneck_report: Dict[str, Any],
    data_dictionary: Dict[str, Any],
    schema_summary: str,
    kpi_config: Dict[str, Any],
) -> str:
    """
    LLM에게 특정 병목 구간의 후보 feature를 제안받는다.
    KPI의 정확한 start/end 컬럼을 명시적으로 전달해, LLM이 이 병목 구간과
    무관한 timestamp를 "직접 변수"로 잘못 제안하지 않도록 한다.
    API 호출 실패 시에도 파이프라인이 죽지 않도록 예외를 처리한다.

    Args:
        stage_name: 병목 구간 이름 (예: "Carrier Delivery")
        bottleneck_report: bottleneck_report.json 파싱 결과
        data_dictionary: data_dictionary.json 파싱 결과
        schema_summary: schema_summary.md 내용
        kpi_config: kpi_definition.yaml 파싱 결과 (processes에서
            stage_name과 일치하는 start/end를 찾아 전달)

    Returns:
        str: Markdown 형식의 후보 feature 목록 (실패 시 안내 메시지)

    Raises:
        ValueError: kpi_config의 processes에서 stage_name을 찾을 수 없는 경우
    """
    stage_info = next(
        (s for s in bottleneck_report["stage_summary"] if s["stage_name"] == stage_name),
        None,
    )
    delay_info = next(
        (d for d in bottleneck_report["delayed_vs_normal"] if d["stage_name"] == stage_name),
        None,
    )
    kpi_definition = next(
        (p for p in kpi_config.get("processes", []) if p["name"] == stage_name),
        None,
    )
    if kpi_definition is None:
        raise ValueError(f"kpi_definition.yaml의 processes에서 '{stage_name}'을 찾을 수 없습니다.")

    user_content = json.dumps({
        "target_stage": stage_name,
        "target_kpi_definition": {
            "start": kpi_definition["start"],
            "end": kpi_definition["end"],
            "meaning": f"{kpi_definition['start']} 시점부터 {kpi_definition['end']} 시점까지의 소요시간",
        },
        "stage_summary": stage_info,
        "delayed_vs_normal": delay_info,
        "data_dictionary": {k: v for k, v in data_dictionary.items() if k != "table_relationships"},
        "table_relationships": data_dictionary.get("table_relationships", []),
        "schema_summary": schema_summary,
    }, ensure_ascii=False)

    try:
        client = get_anthropic_client()
        response = await client.messages.create(
            model=CHAT_MODEL,
            max_tokens=1500,
            system=CANDIDATE_FEATURE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        text_blocks = [block.text for block in response.content if block.type == "text"]
        if not text_blocks:
            raise RuntimeError("응답에 텍스트 블록이 없습니다.")
        content = text_blocks[0].strip()
        log(f"candidate_features 생성 완료: {stage_name}")
        return content
    except Exception as e:
        log(f"candidate_features 생성 실패 ({stage_name}): {e}")
        return (
            f"## Candidate Features for {stage_name}\n\n"
            f"⚠️ LLM 호출 실패로 자동 생성하지 못했습니다.\n\n오류: {e}\n\n"
            "data_dictionary.json을 직접 참고해 후보를 정의해주세요."
        )


async def run_step1(
    config_dir: str = CONFIG_DIR,
    output_dir: str = OUTPUT_DIR,
) -> Dict[str, str]:
    """
    ④ RCA Step 1 실행: bottleneck_report.json의 각 병목 구간에 대해
    candidate_features_{stage}.md 를 생성.
    각 병목의 정확한 KPI 정의(start/end)를 kpi_definition.yaml에서
    가져와 LLM에게 전달한다.

    Args:
        config_dir: kpi_definition.yaml이 있는 폴더
        output_dir: bottleneck_report.json 등이 있고 결과물을 저장할 폴더

    Returns:
        Dict[str, str]: stage_name → candidate_features 파일 경로
    """
    output_dir = ensure_dir(output_dir)

    bottleneck_report = load_json(str(Path(output_dir) / "bottleneck_report.json"))
    data_dictionary = load_json(str(Path(output_dir) / "data_dictionary.json"))
    schema_summary = load_text(str(Path(output_dir) / "schema_summary.md"))
    kpi_config = load_yaml(str(Path(config_dir) / "kpi_definition.yaml"))

    bottlenecks = bottleneck_report.get("bottlenecks", [])
    if not bottlenecks:
        raise RuntimeError("bottleneck_report.json에 판정된 병목(bottlenecks)이 없습니다.")

    results = {}
    for stage_name in bottlenecks:
        content = await suggest_candidate_features(
            stage_name, bottleneck_report, data_dictionary, schema_summary, kpi_config
        )
        safe_name = stage_name.lower().replace(" ", "_")
        file_path = Path(output_dir) / f"candidate_features_{safe_name}.md"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        results[stage_name] = str(file_path)
        log(f"candidate_features 저장 완료: {file_path}")

    return results


# =========================
# 3. Step 2: η² / r² 계산
# =========================
def load_dataframes_for_join(data_dir: str, tables_needed: List[str]) -> Dict[str, pd.DataFrame]:
    """
    join_engine.build_analysis_dataset()에 필요한 테이블만 CSV에서 로드

    Args:
        data_dir: raw CSV 폴더 경로
        tables_needed: 로드할 테이블명 목록 (data_dictionary.json의 키와 동일,
            예: "olist_customers_dataset")

    Returns:
        Dict[str, pd.DataFrame]: {테이블명: DataFrame}
    """
    dataframes = {}
    for table in tables_needed:
        path = Path(data_dir) / f"{table}.csv"
        dataframes[table] = pd.read_csv(path)
        log(f"조인용 테이블 로드: {table} ({len(dataframes[table])}행)")
    return dataframes


def add_derived_columns(df: pd.DataFrame, derived_config: Dict[str, Any]) -> pd.DataFrame:
    """
    approved_features.yaml의 derived 설정대로 파생 컬럼 생성

    Args:
        df: 대상 DataFrame (source 컬럼이 datetime 타입이어야 함)
        derived_config: approved_features.yaml의 해당 stage의 derived 딕셔너리
            예: {"carrier_month": {"source": "order_delivered_carrier_date", "extract": "month"}}

    Returns:
        pd.DataFrame: 파생 컬럼이 추가된 DataFrame
    """
    df = df.copy()
    for new_col, spec in derived_config.items():
        source_col = spec["source"]
        extract = spec["extract"]
        if source_col not in df.columns:
            log(f"파생 컬럼 생성 실패: {source_col}이 df에 없음 ({new_col})")
            continue
        if extract == "month":
            df[new_col] = df[source_col].dt.month
        elif extract == "dayofweek":
            df[new_col] = df[source_col].dt.dayofweek
        elif extract == "hour":
            df[new_col] = df[source_col].dt.hour
        else:
            log(f"지원하지 않는 extract 방식: {extract} ({new_col})")
            continue
        log(f"파생 컬럼 생성: {new_col} = {source_col}.{extract}")
    return df


MIN_GROUP_COUNT_FOR_EXTREMES = 50  # ⑤ Business Impact Simulation의 min_count와 동일


def attach_group_labels(result: Dict[str, Any], derived: Dict[str, Any]) -> Dict[str, Any]:
    """
    group_stats의 극값 그룹에 사람이 읽는 label을 붙인다.

    파생 변수(월/요일)는 값이 정수라 LLM이 오해한다 — dayofweek=0을 "일요일"로
    읽은 사례가 있었다. 라벨을 명시해 프롬프트가 그것을 인용하게 한다.
    파생이 아닌 변수는 값 그대로 label로 쓴다.

    Args:
        result: eta_squared()의 반환값
        derived: approved_features.yaml의 derived 정의

    Returns:
        Dict[str, Any]: highest/lowest에 label이 추가된 새 dict
    """
    stats_block = result.get("group_stats")
    if not stats_block:
        return result
    spec = derived.get(result["variable"], {})
    extract = spec.get("extract")
    labeled = {
        key: {**grp, "label": format_derived_value(grp["group"], extract) if extract else grp["group"]}
        for key, grp in stats_block.items()
        if key in ("highest", "lowest")
    }
    return {**result, "group_stats": {**stats_block, **labeled}}


def eta_squared(df: pd.DataFrame, feature_col: str, target_col: str) -> Dict[str, Any]:
    """
    범주형 변수의 η² (effect size) 계산. ANOVA(F-test) 기반.

    η²와 함께 그룹 극값(group_stats)을 반환한다. Step 3의 LLM이 해석 문장에
    "SP 134h → RR 624h, 4.6배"처럼 실제 수치를 인용할 수 있게 하기 위해서다.
    이 수치가 없으면 LLM은 지어내지 말라는 지시에 따라 일반론만 쓰게 된다.
    극값은 표본이 너무 작은 그룹이 튀는 것을 막기 위해 min_count 이상인
    그룹 중에서만 고른다.

    Args:
        df: 대상 DataFrame
        feature_col: 범주형 변수 컬럼명
        target_col: 대상(연속형) KPI 컬럼명

    Returns:
        Dict[str, Any]: {"variable", "type", "f_stat", "p_value", "effect_size_pct",
        "group_stats": {"highest", "lowest", "ratio", "n_groups"}}
    """
    clean = df[[feature_col, target_col]].dropna()
    grouped = clean.groupby(feature_col)[target_col]
    groups = [g.values for _, g in grouped if len(g) > 0]

    if len(groups) < 2:
        log(f"η² 계산 불가 (그룹 수 부족): {feature_col}")
        return {"variable": feature_col, "type": "categorical", "f_stat": None, "p_value": None, "effect_size_pct": None}

    f_stat, p_value = stats.f_oneway(*groups)

    all_values = np.concatenate(groups)
    grand_mean = np.mean(all_values)
    ss_total = np.sum((all_values - grand_mean) ** 2)
    ss_between = np.sum([len(g) * (np.mean(g) - grand_mean) ** 2 for g in groups])
    eta_sq = ss_between / ss_total if ss_total else 0.0

    # 그룹 극값 (min_count 이상인 그룹만 대상)
    means = grouped.mean()
    counts = grouped.size()
    eligible = means[counts >= MIN_GROUP_COUNT_FOR_EXTREMES]
    group_stats = None
    if len(eligible) >= 2:
        hi, lo = eligible.idxmax(), eligible.idxmin()
        group_stats = {
            "highest": {"group": str(hi), "mean": round(float(eligible[hi]), 1), "n": int(counts[hi])},
            "lowest": {"group": str(lo), "mean": round(float(eligible[lo]), 1), "n": int(counts[lo])},
            "ratio": round(float(eligible[hi] / eligible[lo]), 1) if eligible[lo] else None,
            "n_groups": int(len(eligible)),
        }

    log(f"η² 계산: {feature_col} → F={f_stat:.2f}, p={p_value:.4f}, η²={eta_sq*100:.2f}%")
    return {
        "variable": feature_col,
        "type": "categorical",
        "group_stats": group_stats,
        "f_stat": round(float(f_stat), 2),
        "p_value": round(float(p_value), 4),
        "effect_size_pct": round(float(eta_sq) * 100, 2),
    }


def r_squared(df: pd.DataFrame, feature_col: str, target_col: str) -> Dict[str, Any]:
    """
    연속형 변수의 r² (effect size) 계산. Pearson 상관계수의 제곱.

    Args:
        df: 대상 DataFrame
        feature_col: 연속형 변수 컬럼명
        target_col: 대상(연속형) KPI 컬럼명

    Returns:
        Dict[str, Any]: {"variable", "type", "correlation", "p_value", "effect_size_pct"}
    """
    clean = df[[feature_col, target_col]].dropna()
    corr, p_value = stats.pearsonr(clean[feature_col], clean[target_col])

    log(f"r² 계산: {feature_col} → corr={corr:.4f}, p={p_value:.4f}, r²={corr**2*100:.2f}%")
    return {
        "variable": feature_col,
        "type": "continuous",
        "correlation": round(float(corr), 4),
        "p_value": round(float(p_value), 4),
        "effect_size_pct": round(float(corr ** 2) * 100, 2),
    }


def plot_effect_size(results: List[Dict[str, Any]], stage_name: str, output_path: str) -> None:
    """
    변수별 effect size(%) bar chart 생성

    Args:
        results: eta_squared()/r_squared() 결과 리스트
        stage_name: 병목 구간 이름 (차트 제목용)
        output_path: 저장할 png 경로
    """
    df = pd.DataFrame(results).sort_values("effect_size_pct", ascending=False)
    plt.figure(figsize=(10, 5))
    plt.bar(df["variable"], df["effect_size_pct"], color="mediumpurple")
    plt.xlabel("Variable")
    plt.ylabel("Effect Size (%)")
    plt.title(f"{stage_name} - Effect Size by Variable")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    log(f"effect_size 차트 저장 완료: {output_path}")


def find_base_table_name(data_dictionary: Dict[str, Any], processed_df: pd.DataFrame) -> str:
    """
    processed_dataset과 대응되는 원본 테이블명을 data_dictionary.json에서 찾는다.
    "order_id 컬럼을 가지고 있고, kpi_definition.yaml의 base_table_file에서
    유래한 원본 테이블"을 찾기 위해, order_id를 가진 테이블 중 첫 번째를 사용한다.
    (Olist는 orders 테이블 하나만 base_table로 쓰므로 모호함이 없다.)

    Args:
        data_dictionary: data_dictionary.json 파싱 결과
        processed_df: processed_dataset (참고용, 현재는 컬럼 존재 여부만 확인)

    Returns:
        str: base_table 테이블명

    Raises:
        RuntimeError: order_id 컬럼을 가진 테이블을 찾지 못한 경우
    """
    for table_name, table_info in data_dictionary.items():
        if table_name == "table_relationships":
            continue
        columns = table_info.get("columns", {})
        if "order_id" in columns and "order_purchase_timestamp" in columns:
            return table_name
    raise RuntimeError("data_dictionary.json에서 base_table(orders 테이블)을 찾지 못했습니다.")


async def run_step2_for_stage(
    stage_name: str,
    kpi_col: str,
    approved_features: Dict[str, Any],
    processed_df: pd.DataFrame,
    data_dictionary: Dict[str, Any],
    data_dir: str,
    output_dir: str,
) -> Dict[str, Any]:
    """
    (docstring 동일, 생략)
    """
    from join_engine import build_relationship_graph, find_join_path

    categorical = approved_features.get("categorical", [])
    continuous = approved_features.get("continuous", [])
    derived = approved_features.get("derived", {})

    derived_names = set(derived.keys())
    df_with_derived = add_derived_columns(processed_df, derived)

    all_features = set(categorical) | set(continuous)
    non_derived_features = all_features - derived_names

    target_tables = set()
    for col in non_derived_features:
        for table_name, table_info in data_dictionary.items():
            if table_name == "table_relationships":
                continue
            if col in table_info.get("columns", {}):
                target_tables.add(table_name)
                break

    base_table = find_base_table_name(data_dictionary, processed_df)

    # 경로에 등장하는 모든 경유 테이블까지 포함해서 tables_needed를 완성
    tables_needed = set()
    if target_tables:
        graph = build_relationship_graph(data_dictionary["table_relationships"])
        for target in target_tables:
            path = find_join_path(base_table, target, graph)
            for step in path:
                tables_needed.add(step["to_table"])

    merged_df = df_with_derived
    if tables_needed:
        raw_dataframes = load_dataframes_for_join(data_dir, list(tables_needed))
        raw_dataframes[base_table] = df_with_derived
        merged_df = build_analysis_dataset(
            raw_dataframes, base_table, list(target_tables), data_dictionary["table_relationships"]
        )
        log(f"{stage_name}: 조인 후 {len(merged_df)}행 (원본 {len(df_with_derived)}행)")

    results = []
    for col in categorical:
        results.append(attach_group_labels(eta_squared(merged_df, col, kpi_col), derived))
    for col in continuous:
        results.append(r_squared(merged_df, col, kpi_col))

    safe_name = stage_name.lower().replace(" ", "_")
    chart_path = Path(output_dir) / f"effect_size_{safe_name}.png"
    plot_effect_size(results, stage_name, str(chart_path))

    return {"stage": stage_name, "kpi_column": kpi_col, "effect_sizes": results}


async def run_step2(
    config_dir: str = CONFIG_DIR,
    data_dir: str = DATA_DIR,
    output_dir: str = OUTPUT_DIR,
) -> Dict[str, str]:
    """
    ④ RCA Step 2 전체 실행: bottleneck_report.json의 각 병목 구간에 대해
    approved_features.yaml에 승인된 변수들의 effect size를 계산하고
    effect_size_report.json + effect_size_{stage}.png를 생성한다.

    Args:
        config_dir: kpi_definition.yaml, approved_features.yaml이 있는 폴더
        data_dir: raw CSV 폴더 경로
        output_dir: bottleneck_report.json, processed_dataset.parquet 등이
            있고 결과물을 저장할 폴더

    Returns:
        Dict[str, str]: 생성된 파일 경로들
    """
    output_dir = ensure_dir(output_dir)

    bottleneck_report = load_json(str(Path(output_dir) / "bottleneck_report.json"))
    data_dictionary = load_json(str(Path(output_dir) / "data_dictionary.json"))
    kpi_config = load_yaml(str(Path(config_dir) / "kpi_definition.yaml"))
    approved_features_all = load_yaml(str(Path(config_dir) / "approved_features.yaml"))

    processed_path = Path(output_dir) / "processed_dataset.parquet"
    if not processed_path.exists():
        raise RuntimeError(f"{processed_path}가 없습니다. preprocessing.run()을 먼저 실행하세요.")
    processed_df = pd.read_parquet(processed_path)

    bottlenecks = bottleneck_report.get("bottlenecks", [])
    if not bottlenecks:
        raise RuntimeError("bottleneck_report.json에 판정된 병목(bottlenecks)이 없습니다.")

    stage_results = []
    for stage_name in bottlenecks:
        kpi_definition = next(
            (p for p in kpi_config.get("processes", []) if p["name"] == stage_name), None
        )
        if kpi_definition is None:
            raise ValueError(f"kpi_definition.yaml에서 '{stage_name}'을 찾을 수 없습니다.")
        kpi_col = kpi_definition["kpi_column"]

        safe_name = stage_name.lower().replace(" ", "_")
        approved_features = approved_features_all.get(safe_name)
        if approved_features is None:
            raise ValueError(f"approved_features.yaml에서 '{safe_name}'을 찾을 수 없습니다.")

        stage_result = await run_step2_for_stage(
            stage_name, kpi_col, approved_features, processed_df, data_dictionary, data_dir, output_dir
        )
        stage_results.append(stage_result)

    report_path = Path(output_dir) / "effect_size_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"stages": stage_results}, f, ensure_ascii=False, indent=2)
    log(f"effect_size_report.json 저장 완료: {report_path}")

    return {"effect_size_report": str(report_path)}

# =========================
# 4. Step 3: LLM 결과 해석
# =========================
def filter_significant_causes(
    effect_sizes: List[Dict[str, Any]],
    threshold_pct: float = 2.0,
) -> List[Dict[str, Any]]:
    """
    effect_size_pct가 threshold_pct 이상인 변수만 Root Cause 후보로 남긴다.
    모두 threshold 미만이면, 상대적으로 가장 영향력이 큰 변수 1개는
    남긴다(빈 결과를 방지).

    노트북에서는 각 병목마다 effect size를 보고 "감(직관)"으로 상위
    변수만 fishbone에 채택했다. 이 판단을 Agent에서는 재현 가능한
    규칙(effect_size_pct >= 2%)으로 표준화했다. 병목마다 채택되는
    변수 개수가 고정되지 않고 데이터 자체의 크기 차이를 그대로
    반영한다는 점에서, 고정 Top-N보다 데이터를 존중하는 방식이다.

    Args:
        effect_sizes: eta_squared()/r_squared() 결과 리스트
        threshold_pct: 채택 기준 effect_size_pct (기본 2.0%)

    Returns:
        List[Dict[str, Any]]: threshold 이상인 항목들. 하나도 없으면
        effect_size_pct가 가장 큰 항목 1개를 담은 리스트.
    """
    valid = [e for e in effect_sizes if e.get("effect_size_pct") is not None]
    selected = [e for e in valid if e["effect_size_pct"] >= threshold_pct]

    if not selected and valid:
        selected = [max(valid, key=lambda e: e["effect_size_pct"])]

    log(f"Root Cause 필터링: {len(effect_sizes)}개 → {len(selected)}개 (threshold={threshold_pct}%)")
    return selected


ROOTCAUSE_SYSTEM_PROMPT = """당신은 이커머스 물류 데이터 분석 전문가입니다.
주어진 effect size 분석 결과(η²/r²)를 보고, 이 병목 구간의 Root Cause를
해석하고 두 가지 JSON을 출력하세요.

⚠️ 매우 중요: causes에는 입력으로 주어진 effect_sizes 목록에 실제로
존재하는 variable만 사용하세요. 입력에 없는 변수를 지어내지 마세요.

각 변수(variable)마다, 그 변수가 왜 이 병목에 영향을 줄 수 있는지
일반적인 물류/이커머스 도메인 지식을 활용해 정확히 3개의 구체적인
원인 후보를 details로 작성하세요 (3개보다 많거나 적으면 안 됩니다).
details는 완전한 문장이 아니라 5단어 이내의 짧은 키워드 구문으로
작성하세요 (예: "Remote northern regions", "Weekend processing lag",
"Limited logistics infrastructure"). 단, 입력 변수의 의미를 벗어나는
엉뚱한 원인을 만들지 마세요 (예: customer_state라면 지역/거리/인프라
관련 원인만, product_weight_g라면 무게/포장 관련 원인만).


⚠️ 언어 규칙 (용도가 다르므로 분리):
- details와 카테고리명(category/name): 영어. graphviz 다이어그램 라벨로
  렌더링되며 기본 폰트가 한글을 지원하지 않습니다.
- top_causes의 explanation과 summary: 한국어. 경영진 대상 슬라이드에
  실리는 문장이며 나머지 덱이 전부 한국어입니다.

⚠️ explanation에는 반드시 입력의 group_stats 수치를 인용하세요.
group_stats가 있는 변수는 "가장 낮은 그룹 → 가장 높은 그룹, N배" 형태로
실제 값을 쓰세요 (예: "SP 134h → RR 624h로 4.6배 차이"). 단위는 입력
KPI의 단위(hours)를 그대로 쓰고 h로 표기하세요.
그룹 이름은 반드시 group_stats의 "label" 값을 그대로 쓰세요. "group"의
원시값(0, 5.0 등)을 요일이나 월로 스스로 해석하지 마세요 — label이
이미 정확한 이름("토요일", "3월")입니다. group_stats가 없는
변수(연속형)는 effect_size_pct만 인용하세요. 입력에 없는 숫자를
만들지 마세요.

작업 순서:
1. 각 변수를 상위 카테고리로 그룹핑하세요 (Geography, Seasonality,
   Product Category, Physical Characteristics 등 자유롭게 명명,
   카테고리명도 영어로).
2. 각 카테고리의 effect_size는 소속 변수들의 effect_size_pct 합계로
   계산하세요.
3. Root Cause 순위는 카테고리 effect_size 기준 내림차순입니다.

반드시 아래 두 개의 JSON을 순서대로, 다른 설명 없이 출력하세요.

=== JSON 1: rootcause_report ===
{
  "stage": "<stage_key>",
  "top_causes": [
    {"category": "<영어 카테고리명>", "effect_size_pct": <숫자>, "explanation": "한국어 한 문장, group_stats 수치 인용"}
  ],
  "summary": "한국어 2-3문장 요약"
}

=== JSON 2: cause_effect_structure ===
{
  "stage": "<stage_key>",
  "problem": "<Stage Name> Delay",
  "categories": [
    {
      "name": "<카테고리명>",
      "effect_size": <숫자>,
      "causes": [
        {
          "variable": "<입력에 실제로 있던 variable명>",
          "details": ["Short keyword phrase 1", "Short keyword phrase 2", "Short keyword phrase 3"]
        }
      ]
    }
  ]
}
"""

async def interpret_effect_size(
    stage_name: str,
    stage_key: str,
    effect_sizes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    LLM에게 effect_size_report의 한 stage 결과를 전달해 Root Cause 해석과
    cause_effect_structure를 받는다. API 실패 시에도 파이프라인이 죽지
    않도록 예외를 처리한다.

    Args:
        stage_name: 병목 구간 이름 (예: "Carrier Delivery")
        stage_key: safe_name (예: "carrier_delivery")
        effect_sizes: effect_size_report.json의 해당 stage의 effect_sizes 리스트

    Returns:
        Dict[str, Any]: {"rootcause_report": {...}, "cause_effect_structure": {...}}
        (실패 시 두 값 모두 fallback 딕셔너리)
    """
    user_content = json.dumps({
        "stage": stage_key,
        "stage_name": stage_name,
        "effect_sizes": effect_sizes,
    }, ensure_ascii=False)

    fallback = {
        "rootcause_report": {
            "stage": stage_key,
            "top_causes": [],
            "summary": "LLM 호출 실패로 해석을 생성하지 못했습니다. effect_size_report.json을 직접 참고하세요.",
        },
        "cause_effect_structure": {
            "stage": stage_key,
            "problem": f"{stage_name} Delay",
            "categories": [],
        },
    }

    try:
        client = get_anthropic_client()
        response = await client.messages.create(
            model=CHAT_MODEL,
            max_tokens=2000,
            system=ROOTCAUSE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        text_blocks = [block.text for block in response.content if block.type == "text"]
        if not text_blocks:
            raise RuntimeError("응답에 텍스트 블록이 없습니다.")
        content = text_blocks[0].strip()

        # 코드블록이든 아니든, 텍스트 안에서 '{'로 시작하는 JSON 객체를
        # 순서대로 두 개 찾아 파싱한다. json.JSONDecoder.raw_decode는
        # 문자열 맨 앞이 반드시 JSON이어야 하므로, 첫 '{'의 위치부터
        # 잘라서 넘겨야 한다.
        decoder = json.JSONDecoder()

        first_brace = content.index("{")
        rootcause_report, end_idx = decoder.raw_decode(content, first_brace)

        remainder = content[first_brace + end_idx:]
        second_brace = remainder.index("{")
        cause_effect_structure, _ = decoder.raw_decode(remainder, second_brace)

        log(f"rootcause 해석 완료: {stage_name}")
        return {"rootcause_report": rootcause_report, "cause_effect_structure": cause_effect_structure}
    except Exception as e:
        log(f"rootcause 해석 실패 ({stage_name}): {e}")
        return fallback


async def run_step3(
    output_dir: str = OUTPUT_DIR,
) -> Dict[str, str]:
    """
    ④ RCA Step 3 전체 실행: effect_size_report.json의 각 stage에 대해
    LLM이 Root Cause를 해석하고, rootcause_report.json +
    cause_effect_structure_{stage}.json을 생성한다.

    Args:
        output_dir: effect_size_report.json이 있고 결과물을 저장할 폴더

    Returns:
        Dict[str, str]: 생성된 파일 경로들
    """
    output_dir = ensure_dir(output_dir)

    effect_size_report = load_json(str(Path(output_dir) / "effect_size_report.json"))

    all_rootcause = []
    structure_paths = {}

    for stage_data in effect_size_report["stages"]:
        stage_name = stage_data["stage"]
        stage_key = stage_name.lower().replace(" ", "_")

        significant_causes = filter_significant_causes(stage_data["effect_sizes"], threshold_pct=2.0)
        result = await interpret_effect_size(stage_name, stage_key, significant_causes)
        all_rootcause.append(result["rootcause_report"])

        structure_path = Path(output_dir) / f"cause_effect_structure_{stage_key}.json"
        with open(structure_path, "w", encoding="utf-8") as f:
            json.dump(result["cause_effect_structure"], f, ensure_ascii=False, indent=2)
        structure_paths[stage_key] = str(structure_path)
        log(f"cause_effect_structure 저장 완료: {structure_path}")

    rootcause_path = Path(output_dir) / "rootcause_report.json"
    with open(rootcause_path, "w", encoding="utf-8") as f:
        json.dump({"stages": all_rootcause}, f, ensure_ascii=False, indent=2)
    log(f"rootcause_report.json 저장 완료: {rootcause_path}")

    return {"rootcause_report": str(rootcause_path), **structure_paths}

# =========================
# 5. Step 4: graphviz 다이어그램 생성
# =========================
import graphviz


def build_cause_effect_diagram(structure: Dict[str, Any]) -> graphviz.Digraph:
    """
    cause_effect_structure.json 스키마를 받아 트리 형태의 graphviz Digraph 생성.
    Problem을 중심 노드로, 각 카테고리를 1단계 자식으로, 각 카테고리의
    causes(변수 + 세부 원인 details)를 2단계 자식으로 배치한다.

    Args:
        structure: cause_effect_structure_{stage}.json 파싱 결과

    Returns:
        graphviz.Digraph: 렌더링 전 그래프 객체
    """
    dot = graphviz.Digraph(comment=structure["problem"])
    dot.attr(rankdir="LR")
    dot.attr("node", shape="box", style="rounded,filled", fontname="Helvetica")

    problem_node = "PROBLEM"
    dot.node(problem_node, structure["problem"], fillcolor="lightcoral", fontsize="14")

    for category in structure["categories"]:
        cat_node = f"cat_{category['name'].replace(' ', '_')}"
        cat_label = f"{category['name']}\n({category['effect_size']}%)"
        dot.node(cat_node, cat_label, fillcolor="lightblue")
        dot.edge(cat_node, problem_node)

        for i, cause in enumerate(category["causes"]):
            cause_node = f"cause_{category['name']}_{i}"
            details = cause.get("details", [cause.get("variable", "")])
            label = "\n".join(f"• {d}" for d in details)
            dot.node(cause_node, label, fillcolor="lightyellow", fontsize="9")
            dot.edge(cause_node, cat_node)

    return dot


def run_step4(output_dir: str = OUTPUT_DIR) -> Dict[str, str]:
    """
    ④ RCA Step 4 실행: 각 cause_effect_structure_{stage}.json을 읽어
    graphviz 트리 다이어그램(cause_effect_diagram_{stage}.png)을 생성한다.

    Args:
        output_dir: cause_effect_structure_{stage}.json이 있고 결과물을
            저장할 폴더

    Returns:
        Dict[str, str]: stage_key → 생성된 png 경로
    """
    output_dir = ensure_dir(output_dir)

    structure_files = list(Path(output_dir).glob("cause_effect_structure_*.json"))
    if not structure_files:
        raise RuntimeError(f"{output_dir}에 cause_effect_structure_*.json이 없습니다. run_step3()을 먼저 실행하세요.")

    results = {}
    for structure_path in structure_files:
        structure = load_json(str(structure_path))
        stage_key = structure["stage"]

        dot = build_cause_effect_diagram(structure)
        output_path = Path(output_dir) / f"cause_effect_diagram_{stage_key}"
        try:
            rendered_path = dot.render(str(output_path), format="png", cleanup=True)
        except graphviz.backend.ExecutableNotFound:
            # 시스템 Graphviz(dot)가 없으면 다이어그램만 건너뛴다. 파이프라인의 다른
            # 산출물은 이 이미지에 의존하지 않고, PPT 렌더러는 이미지가 없으면
            # 플레이스홀더를 표시한다. 여기서 죽으면 ⑤~⑨를 전부 잃는다.
            log(f"⚠️ Graphviz 실행파일(dot)이 없어 {stage_key} 다이어그램을 건너뜁니다. "
                f"설치: https://graphviz.org/download/ (PATH 등록 필요)")
            # render()는 dot 호출 전에 .gv 소스를 먼저 쓰므로 실패 시 잔여물이 남는다
            Path(str(output_path)).unlink(missing_ok=True)
            continue

        results[stage_key] = rendered_path
        log(f"cause_effect_diagram 저장 완료: {rendered_path}")

    return results