# data_understanding.py
"""
① ERD 생성 및 데이터 이해 모듈
- raw CSV들을 읽어 컬럼 구조/타입/결측치 파악
- 컬럼명 매칭 + 값 검증으로 테이블 간 관계 확정
  (Assumption: PK/FK는 동일한 컬럼명을 사용한다)
- LLM으로 스키마의 비즈니스 의미 설명 생성 (schema_summary.md)

범용성: 이커머스 데이터 일반에 적용 가능하도록 설계.
특정 데이터셋(예: Olist)의 파일명 규칙에 종속되지 않으며,
테이블명은 파일명(확장자 제외)을 그대로 사용한다.

table_relationships의 역할 (Purpose):
1. 데이터 구조를 LLM이 이해하기 위한 참고 정보
2. Python Tool이 분석용 데이터셋 생성 시 join path와 join key를
   자동으로 결정하기 위한 메타데이터 (실제 조인 경로 탐색/실행은
   join_engine.py가 담당)
"""

from __future__ import annotations
import json
from pathlib import Path
from itertools import combinations
from typing import Any, Dict, List
import pandas as pd
from config import DATA_DIR, OUTPUT_DIR, CHAT_MODEL, ensure_dir, get_anthropic_client, log


# =========================
# 1. CSV 로딩
# =========================
def load_all_csvs(data_dir: str = DATA_DIR) -> Dict[str, pd.DataFrame]:
    """
    data_dir 안의 raw CSV들을 전부 읽어 테이블명: DataFrame 딕셔너리로 반환.
    테이블명은 파일명(확장자 제외)을 그대로 사용한다.
    특정 데이터셋의 파일명 규칙(예: Olist의 "olist_" 접두어, "_dataset" 접미어)에
    종속되지 않도록, 접두/접미어 제거 로직을 두지 않는다.

    Args:
        data_dir: CSV들이 있는 폴더 경로

    Returns:
        Dict[str, pd.DataFrame]: {"olist_orders_dataset": df, ...}
        (파일명 그대로가 키가 됨. kpi_definition.yaml 등에서
        이 파일명 그대로 base_table 등을 지정해 사용한다.)
    """
    dataframes = {}
    for path in Path(data_dir).glob("*.csv"):
        table_name = path.stem  # 파일명 그대로 사용
        try:
            dataframes[table_name] = pd.read_csv(path)
            log(f"로드 완료: {table_name} ({len(dataframes[table_name])}행)")
        except Exception as e:
            log(f"로드 실패: {path.name} - {e}")
    return dataframes


# =========================
# 2. 컬럼 구조 추출
# =========================
def extract_columns_info(df: pd.DataFrame) -> Dict[str, Any]:
    """
    단일 테이블의 컬럼별 dtype, 결측치 비율, 샘플값 추출

    Args:
        df: 대상 DataFrame

    Returns:
        Dict[str, Any]: 컬럼명별 메타 정보
    """
    columns = {}
    for col in df.columns:
        columns[col] = {
            "dtype": str(df[col].dtype),
            "null_ratio": round(float(df[col].isnull().mean()), 4),
            "unique_ratio": round(float(df[col].nunique() / len(df)), 4) if len(df) else 0.0,
            "sample_values": [str(v) for v in df[col].dropna().head(3).tolist()],
        }
    return columns


# =========================
# 3. 테이블 관계 탐지 (컬럼명 매칭 + 값 검증, 방향 추측 없음)
# =========================
def verify_overlap(series_a: pd.Series, series_b: pd.Series) -> float:
    """
    series_a의 값들이 series_b에 얼마나 포함되는지 비율 계산

    Args:
        series_a: 기준이 되는 컬럼
        series_b: 비교 대상 컬럼

    Returns:
        float: 겹침 비율 (0.0 ~ 1.0), series_a 기준
    """
    set_a = set(series_a.dropna().unique())
    set_b = set(series_b.dropna().unique())
    if not set_a:
        return 0.0
    return len(set_a & set_b) / len(set_a)

def find_table_relationships(dataframes: Dict[str, pd.DataFrame], threshold: float = 0.9) -> List[Dict[str, Any]]:
    """
    컬럼명이 동일한 컬럼들을 관계 후보로 묶고, 값 겹침을 검증해 관계를 확정

    전제조건(Assumption): PK/FK는 동일한 컬럼명을 사용한다.
    (예: customer_id, seller_id, order_id, product_id)

    주의: 어느 쪽이 PK이고 어느 쪽이 FK인지 방향은 판단하지 않는다.
    유니크 비율만으로 방향을 추측하면 두 테이블이 모두 1:1 관계라
    유니크 비율이 같은 경우(예: orders-reviews) 방향이 잘못 뒤집힐 수
    있기 때문. 대신 "두 테이블이 이 컬럼으로 연결되어 있다"는 사실만
    기록한다. 방향이 필요한 조인 실행 시점의 로직은 join_engine.py가
    담당한다.

    Args:
        dataframes: {테이블명: DataFrame}
        threshold: 관계로 인정할 최소 겹침 비율

    Returns:
        List[Dict]: 확정된 테이블 관계 목록 (방향 없음)
        예: [{"column": "customer_id", "tables": ["olist_orders_dataset", "olist_customers_dataset"], "overlap_ratio": 1.0}]
    """
    column_owners: Dict[str, List[str]] = {}
    for table, df in dataframes.items():
        for col in df.columns:
            column_owners.setdefault(col, []).append(table)

    candidates = {col: tables for col, tables in column_owners.items() if len(tables) > 1}

    verified = []
    for col, tables in candidates.items():
        for t1, t2 in combinations(tables, 2):
            overlap_1_in_2 = verify_overlap(dataframes[t1][col], dataframes[t2][col])
            overlap_2_in_1 = verify_overlap(dataframes[t2][col], dataframes[t1][col])
            max_overlap = max(overlap_1_in_2, overlap_2_in_1)

            if max_overlap >= threshold:
                verified.append({
                    "column": col,
                    "tables": [t1, t2],
                    "overlap_ratio": round(max_overlap, 3),
                })
    log(f"테이블 관계 탐지 완료: {len(verified)}개 관계 확정")
    return verified


# =========================
# 4. data_dictionary.json 생성
# =========================
def build_data_dictionary(dataframes: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """
    전체 테이블에 대해 컬럼 구조 + 테이블 간 관계를 담은 data_dictionary 생성

    Args:
        dataframes: {테이블명: DataFrame}

    Returns:
        Dict[str, Any]: data_dictionary.json에 저장될 구조
    """
    dictionary = {}
    for table_name, df in dataframes.items():
        dictionary[table_name] = {
            "row_count": len(df),
            "columns": extract_columns_info(df),
        }
    dictionary["table_relationships"] = find_table_relationships(dataframes)
    return dictionary


# =========================
# 5. schema_summary.md 생성 (LLM, 예외 처리 포함)
# =========================
SYSTEM_PROMPT = """당신은 이커머스 데이터 분석 도메인 전문가입니다.
주어진 데이터 딕셔너리(JSON)를 보고, 각 테이블과 주요 컬럼이
비즈니스적으로 어떤 의미를 갖는지 한국어로 설명하는 Markdown 문서를 작성하세요.

규칙:
- 테이블별로 소제목(##)을 달고, 그 테이블의 역할을 한 줄로 요약
- 주요 컬럼(특히 timestamp, id, category 관련)의 의미를 짧게 설명
- table_relationships는 별도 섹션으로 정리 (방향은 알 수 없으니 "A ↔ B" 형태로 표기)
- 불필요한 서론 없이 Markdown 본문만 출력"""

async def generate_schema_summary(data_dictionary: Dict[str, Any]) -> str:
    """
    data_dictionary를 LLM에 전달해 schema_summary.md 내용 생성.
    API 호출 실패 시에도 파이프라인이 죽지 않도록 예외를 처리한다.

    Args:
        data_dictionary: build_data_dictionary()의 결과

    Returns:
        str: Markdown 형식의 스키마 설명 (실패 시 안내 메시지)
    """
    try:
        client = get_anthropic_client()
        response = await client.messages.create(
            model=CHAT_MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(data_dictionary, ensure_ascii=False)}],
        )
        # extended thinking이 켜져 있으면 content[0]이 ThinkingBlock일 수 있으므로
        # type == "text"인 블록만 찾아서 사용한다.
        text_blocks = [block.text for block in response.content if block.type == "text"]
        if not text_blocks:
            raise RuntimeError("응답에 텍스트 블록이 없습니다.")
        content = text_blocks[0].strip()
        log("schema_summary.md 생성 완료")
        return content
    except Exception as e:
        log(f"schema_summary 생성 실패: {e}")
        return (
            "# Schema Summary\n\n"
            f"⚠️ LLM 호출 실패로 자동 생성하지 못했습니다.\n\n오류: {e}\n\n"
            "원본 데이터 구조는 data_dictionary.json을 참고하세요."
        )
# =========================
# 6. 전체 실행 함수
# =========================
async def run(data_dir: str = DATA_DIR, output_dir: str = OUTPUT_DIR) -> Dict[str, str]:
    """
    ① ERD 생성 및 데이터 이해 단계 전체 실행

    Args:
        data_dir: raw CSV 폴더 경로
        output_dir: 결과 저장 폴더 경로

    Returns:
        Dict[str, str]: 생성된 파일 경로들
    """
    output_dir = ensure_dir(output_dir)

    dataframes = load_all_csvs(data_dir)
    if not dataframes:
        raise RuntimeError(f"{data_dir}에서 CSV를 찾지 못했습니다.")

    data_dictionary = build_data_dictionary(dataframes)
    dict_path = Path(output_dir) / "data_dictionary.json"
    with open(dict_path, "w", encoding="utf-8") as f:
        json.dump(data_dictionary, f, ensure_ascii=False, indent=2)

    schema_summary = await generate_schema_summary(data_dictionary)
    summary_path = Path(output_dir) / "schema_summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(schema_summary)

    return {"data_dictionary": str(dict_path), "schema_summary": str(summary_path)}