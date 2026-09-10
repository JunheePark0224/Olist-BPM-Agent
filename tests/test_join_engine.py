"""
join_engine이 "이중 조인을 구조적으로 막는다"는 주장의 실행 가능한 증거.

배경: 수동 노트북(05_Root_Cause_Analysis_2.ipynb)은 order_items를 두 번
조인해 108,581행이 151,581행으로 복제됐고, product_category η²가 8.35%에서
12.77%로 부풀려졌다 (docs/verification.md). join_engine은 merged_tables
집합으로 이미 조인한 테이블을 추적해 같은 실수를 원천 차단한다.

이 테스트는 그 보장을 작은 가짜 테이블로 재현한다.

실행:
    pytest tests/
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent" / "src"))

from join_engine import build_analysis_dataset, build_relationship_graph, find_join_path  # noqa: E402


# =========================
# 픽스처: Olist 구조를 축소한 가짜 테이블
# =========================
@pytest.fixture
def tables() -> dict[str, pd.DataFrame]:
    """
    orders 3건. A는 아이템 2개(셀러 2곳), B·C는 아이템 1개.
    orders → items는 1:N, items → sellers는 N:1.
    """
    return {
        "orders": pd.DataFrame({"order_id": ["A", "B", "C"], "kpi": [10.0, 20.0, 30.0]}),
        "items": pd.DataFrame({
            "order_id": ["A", "A", "B", "C"],
            "seller_id": ["s1", "s2", "s1", "s3"],
            "product_id": ["p1", "p2", "p1", "p3"],
        }),
        "sellers": pd.DataFrame({"seller_id": ["s1", "s2", "s3"], "seller_state": ["SP", "RJ", "SP"]}),
        "products": pd.DataFrame({"product_id": ["p1", "p2", "p3"], "category": ["x", "y", "x"]}),
    }


@pytest.fixture
def relationships() -> list[dict]:
    """data_dictionary.json의 table_relationships 형식."""
    return [
        {"column": "order_id", "tables": ["orders", "items"]},
        {"column": "seller_id", "tables": ["items", "sellers"]},
        {"column": "product_id", "tables": ["items", "products"]},
    ]


# =========================
# 1. 핵심 주장: 같은 테이블은 한 번만 조인된다
# =========================
def test_shared_intermediate_table_is_joined_once(tables, relationships):
    """
    sellers와 products는 둘 다 items를 거쳐야 한다. 노트북은 이 상황에서
    items를 두 번 조인했다. join_engine은 한 번만 조인해야 한다.

    기대 행 수 = items 행 수(4). 이중 조인이면 A의 아이템 2개가 다시
    2배로 펼쳐져 6행이 된다.
    """
    result = build_analysis_dataset(tables, "orders", ["sellers", "products"], relationships)

    assert len(result) == 4, f"items가 두 번 조인되어 행이 복제됨: {len(result)}행"
    assert result["order_id"].value_counts().to_dict() == {"A": 2, "B": 1, "C": 1}


def test_join_order_does_not_change_row_count(tables, relationships):
    """join_tables 순서를 바꿔도 결과 행 수는 같아야 한다."""
    forward = build_analysis_dataset(tables, "orders", ["sellers", "products"], relationships)
    reverse = build_analysis_dataset(tables, "orders", ["products", "sellers"], relationships)

    assert len(forward) == len(reverse) == 4


# =========================
# 2. 조인 경로 탐색
# =========================
def test_find_join_path_routes_through_intermediate(relationships):
    """orders → sellers는 items를 경유해야 한다. BFS가 경유 테이블을 찾아야 한다."""
    graph = build_relationship_graph(relationships)
    path = find_join_path("orders", "sellers", graph)

    assert [step["to_table"] for step in path] == ["items", "sellers"]
    assert path[0]["left_column"] == "order_id"
    assert path[1]["left_column"] == "seller_id"


def test_find_join_path_raises_when_unreachable(relationships):
    """경로가 없는 테이블은 조용히 빈 결과를 주지 않고 즉시 실패해야 한다."""
    graph = build_relationship_graph(relationships)

    with pytest.raises(ValueError, match="조인 경로를 찾을 수 없습니다"):
        find_join_path("orders", "warehouses", graph)


# =========================
# 3. 조인은 base_table의 값을 보존한다
# =========================
def test_base_table_values_are_preserved(tables, relationships):
    """조인 후에도 orders의 KPI 값이 그대로 남아 있어야 한다 (left join)."""
    result = build_analysis_dataset(tables, "orders", ["sellers"], relationships)

    kpi_by_order = result.drop_duplicates("order_id").set_index("order_id")["kpi"].to_dict()
    assert kpi_by_order == {"A": 10.0, "B": 20.0, "C": 30.0}
    assert result["seller_state"].notna().all()
