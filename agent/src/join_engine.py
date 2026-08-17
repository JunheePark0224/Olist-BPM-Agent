# join_engine.py
"""
테이블 관계 그래프 구성 및 조인 실행 엔진
- data_understanding.py가 만든 table_relationships를 그래프로 변환
- BFS로 base_table → target_table 조인 경로 탐색
- 필요한 테이블만 선택적으로 조인해 분석용 데이터셋 생성

이 모듈은 순수 "조인 엔진"이며 특정 파이프라인 단계에 종속되지 않는다.
preprocessing.py, root_cause_analysis.py 등 여러 단계에서
필요할 때마다 이 모듈을 import해서 재사용한다.
"""

from __future__ import annotations
from collections import deque
from typing import Any, Dict, List, Tuple
import pandas as pd
from config import log


def build_relationship_graph(table_relationships: List[Dict[str, Any]]) -> Dict[str, List[Tuple[str, str]]]:
    """
    table_relationships 리스트를 인접 리스트 형태의 그래프로 변환

    Args:
        table_relationships: data_dictionary.json의 table_relationships
            예: [{"column": "customer_id",
                  "tables": ["olist_orders_dataset", "olist_customers_dataset"],
                  "overlap_ratio": 1.0}]

    Returns:
        Dict[str, List[Tuple[str, str]]]: {테이블: [(연결된 테이블, 조인컬럼), ...]}
    """
    graph: Dict[str, List[Tuple[str, str]]] = {}
    for rel in table_relationships:
        t1, t2 = rel["tables"]
        col = rel["column"]
        graph.setdefault(t1, []).append((t2, col))
        graph.setdefault(t2, []).append((t1, col))
    return graph


def find_join_path(base_table: str, target_table: str, graph: Dict[str, List[Tuple[str, str]]]) -> List[Dict[str, str]]:
    """
    base_table에서 target_table까지의 조인 경로를 BFS로 탐색.
    그래프 자체는 방향이 없지만, base_table을 기준으로 탐색하면서
    from_table → to_table 방향을 확정해 반환한다.

    중간에 경유해야 하는 테이블도 자동으로 포함된다.

    Args:
        base_table: 시작 테이블
        target_table: 도달하려는 테이블
        graph: build_relationship_graph()의 결과

    Returns:
        List[Dict]: 순서대로 밟아야 할 조인 경로.
        각 원소: {"from_table", "to_table", "left_column", "right_column"}
        컬럼명이 같다는 Assumption 하에 left_column == right_column이지만,
        추후 컬럼명이 다른 경우로 확장 가능하도록 필드를 분리해 둔다.

    Raises:
        ValueError: 경로를 찾을 수 없는 경우
    """
    if base_table == target_table:
        return []

    visited = {base_table}
    queue = deque([(base_table, [])])

    while queue:
        current, path = queue.popleft()
        for neighbor, col in graph.get(current, []):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            new_step = {
                "from_table": current,
                "to_table": neighbor,
                "left_column": col,
                "right_column": col,
            }
            new_path = path + [new_step]
            if neighbor == target_table:
                return new_path
            queue.append((neighbor, new_path))

    raise ValueError(f"'{base_table}' → '{target_table}' 조인 경로를 찾을 수 없습니다.")


def build_analysis_dataset(
    dataframes: Dict[str, pd.DataFrame],
    base_table: str,
    join_tables: List[str],
    table_relationships: List[Dict[str, Any]],
) -> pd.DataFrame:
    """
    base_table을 기준으로 join_tables에 명시된 테이블들을
    table_relationships의 그래프를 따라 자동으로 조인.
    필요한 테이블만 선택적으로 조인한다 (전체 Wide Table이 아님).

    Args:
        dataframes: {테이블명: DataFrame} (조인에 필요한 테이블만 있어도 됨)
        base_table: 기준 테이블
        join_tables: 조인이 필요한 테이블 목록
        table_relationships: data_dictionary.json의 table_relationships

    Returns:
        pd.DataFrame: 조인 완료된 데이터셋

    Raises:
        ValueError: 조인 경로의 left_column이 현재 df에 존재하지 않는 경우.
            여러 join_tables의 경로가 서로 다른 지점에서 갈라질 때
            아직 조인되지 않은 from_table을 기준으로 병합을 시도하면
            발생할 수 있다. 조용히 잘못된 결과를 만드는 대신 여기서 즉시 멈춘다.
    """
    graph = build_relationship_graph(table_relationships)
    df = dataframes[base_table].copy()
    merged_tables = {base_table}

    for target in join_tables:
        if target in merged_tables:
            continue
        path = find_join_path(base_table, target, graph)
        for step in path:
            if step["to_table"] in merged_tables:
                continue

            if step["left_column"] not in df.columns:
                raise ValueError(
                    f"조인 실패: '{step['from_table']}' 테이블의 컬럼 "
                    f"'{step['left_column']}'이 현재 df에 없습니다. "
                    f"(현재 df 컬럼 수: {len(df.columns)}) "
                    f"'{step['from_table']}'이 먼저 조인되어 있는지 확인하세요."
                )

            df = df.merge(
                dataframes[step["to_table"]],
                left_on=step["left_column"],
                right_on=step["right_column"],
                how="left",
                suffixes=("", f"_{step['to_table']}"),
            )
            merged_tables.add(step["to_table"])

    log(f"분석 데이터셋 조인 완료: {base_table} + {sorted(merged_tables - {base_table})}")
    return df