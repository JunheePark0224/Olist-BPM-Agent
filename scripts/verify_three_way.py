"""
세 가지 분석 방식의 교차 검증 스크립트

같은 Olist 데이터를 세 번 분석했다.
  A. 수동 노트북      (notebooks/05_Root_Cause_Analysis_2.ipynb)
  B. 에이전트 파이프라인 (agent/src/)
  C. 원샷 LLM         (CSV를 한 번에 던져 받은 15장 덱)

이 스크립트는 docs/verification.md에 실린 모든 수치를 원본 데이터에서
다시 계산해, 각 방식의 결과가 맞는지 판정한다.

실행:
    python scripts/verify_three_way.py

의존성: pandas, numpy, scipy  (LLM API 키 불필요)
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "agent" / "outputs"

TOLERANCE = 0.01  # 재현으로 인정할 상대 오차 (1%)


# =========================
# 공통 유틸
# =========================
def eta_squared(df: pd.DataFrame, feature: str, target: str) -> Tuple[float, float]:
    """
    범주형 변수의 F통계량과 η²(%)를 계산한다.

    Args:
        df: 대상 DataFrame
        feature: 범주형 컬럼
        target: 연속형 KPI 컬럼

    Returns:
        Tuple[float, float]: (F통계량, η² 백분율)
    """
    clean = df[[feature, target]].dropna()
    groups = [g[target].values for _, g in clean.groupby(feature)]
    f_stat, _ = stats.f_oneway(*groups)
    values = np.concatenate(groups)
    grand_mean = values.mean()
    ss_total = ((values - grand_mean) ** 2).sum()
    ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in groups)
    return float(f_stat), float(ss_between / ss_total * 100)


class Checker:
    """주장값과 재계산값을 비교해 결과를 누적하는 단순 검증기."""

    def __init__(self) -> None:
        self.rows: List[Dict[str, object]] = []

    def check(self, source: str, name: str, claimed: float, actual: float, unit: str = "") -> None:
        if claimed == 0:
            ok = abs(actual) < 1e-9
        else:
            ok = abs(actual - claimed) / abs(claimed) <= TOLERANCE
        self.rows.append({
            "source": source, "name": name, "claimed": claimed,
            "actual": actual, "unit": unit, "ok": ok,
        })
        mark = "OK  " if ok else "FAIL"
        print(f"  [{mark}] {name:<44} 주장 {claimed:>10,.3f}{unit:<5} 실제 {actual:>10,.3f}{unit}")

    def summary(self) -> None:
        print("\n" + "=" * 78)
        for source in dict.fromkeys(r["source"] for r in self.rows):
            rows = [r for r in self.rows if r["source"] == source]
            passed = sum(1 for r in rows if r["ok"])
            print(f"  {source:<28} {passed}/{len(rows)} 재현")
            for r in rows:
                if not r["ok"]:
                    print(f"      └ 불일치: {r['name']} (주장 {r['claimed']}, 실제 {r['actual']:.4f})")
        print("=" * 78)


# =========================
# A. 수동 노트북 — 이중 조인 검증
# =========================
def verify_notebook_double_join(check: Checker) -> None:
    """
    노트북이 order_items를 두 번 조인해 행이 복제되었는지 검증한다.

    05_Root_Cause_Analysis_2.ipynb는 cell 3에서 items[['order_id','seller_id']]를,
    cell 9에서 다시 items[['order_id','product_id']]를 order_id로 조인한다.
    두 번째 조인 시점에 이미 아이템 단위로 펼쳐진 상태이므로 행이 한 번 더
    불어난다. 조인을 거치지 않는 변수는 영향을 받지 않는다는 점이 결정적이다.
    """
    print("\n[A] 수동 노트북 — order_items 이중 조인")
    orders = pd.read_csv(DATA_DIR / "archive" / "orders_delivered_clean.csv")
    items = pd.read_csv(DATA_DIR / "olist_order_items_dataset.csv")
    products = pd.read_csv(DATA_DIR / "olist_products_dataset.csv")
    translation = pd.read_csv(DATA_DIR / "product_category_name_translation.csv")

    check.check("A. 노트북", "전처리 후 주문 수", 95_082, float(len(orders)), "행")

    # 노트북 재현: items를 두 번 조인
    step1 = orders.merge(items[["order_id", "seller_id"]], on="order_id", how="left")
    step2 = step1.merge(items[["order_id", "product_id"]], on="order_id", how="left")
    notebook_df = (
        step2.merge(products[["product_id", "product_category_name", "product_weight_g"]],
                    on="product_id", how="left")
             .merge(translation, on="product_category_name", how="left")
    )
    check.check("A. 노트북", "1차 조인 후 행 수", 108_581, float(len(step1)), "행")
    check.check("A. 노트북", "2차 조인 후 행 수 (복제됨)", 151_581, float(len(notebook_df)), "행")

    f_nb, eta_nb = eta_squared(notebook_df, "product_category_name_english", "seller_processing_time")
    check.check("A. 노트북", "product_category F통계량", 312.45, f_nb)
    check.check("A. 노트북", "product_category eta^2", 12.77, eta_nb, "%")

    # 올바른 단일 조인
    correct_df = (
        orders.merge(items[["order_id", "seller_id", "product_id"]], on="order_id", how="left")
              .merge(products[["product_id", "product_category_name", "product_weight_g"]],
                     on="product_id", how="left")
              .merge(translation, on="product_category_name", how="left")
    )
    f_ok, eta_ok = eta_squared(correct_df, "product_category_name_english", "seller_processing_time")
    check.check("A. 노트북", "단일 조인 시 행 수", 108_581, float(len(correct_df)), "행")
    check.check("A. 노트북", "단일 조인 시 F통계량", 139.25, f_ok)
    check.check("A. 노트북", "단일 조인 시 eta^2", 8.35, eta_ok, "%")


def verify_untouched_variables(check: Checker) -> None:
    """
    order_items를 거치지 않는 변수는 노트북과 파이프라인이 일치하는지 확인한다.

    이 대조가 핵심이다. 조인 경로를 타지 않는 변수가 소수점까지 같다면,
    앞의 불일치는 계산 방식 차이가 아니라 조인이 만든 것임이 확정된다.
    """
    print("\n[A'] 대조군 — order_items를 거치지 않는 변수는 일치해야 한다")
    orders = pd.read_csv(DATA_DIR / "archive" / "orders_delivered_clean.csv")
    items = pd.read_csv(DATA_DIR / "olist_order_items_dataset.csv")
    sellers = pd.read_csv(DATA_DIR / "olist_sellers_dataset.csv")
    df = (orders.merge(items[["order_id", "seller_id"]], on="order_id", how="left")
                .merge(sellers[["seller_id", "seller_state"]], on="seller_id", how="left"))
    # 노트북과 파이프라인이 동일하게 order_approved_at에서 파생시킨 변수
    approved = pd.to_datetime(df["order_approved_at"])
    df["seller_month"] = approved.dt.month
    df["seller_dayofweek"] = approved.dt.dayofweek

    agent = {"seller_state": 0.28, "seller_month": 1.51, "seller_dayofweek": 2.45}
    for variable, expected in agent.items():
        _, eta = eta_squared(df, variable, "seller_processing_time")
        check.check("A'. 대조군", f"{variable} eta^2 (파이프라인과 동일)", expected, eta, "%")


# =========================
# C. 원샷 LLM 덱 검증
# =========================
def verify_oneshot_deck(check: Checker) -> None:
    """
    원샷 LLM이 생성한 덱의 수치를 원본 데이터로 재계산한다.

    대부분은 소수점까지 일치하지만, 리뷰 관련 4개 값은 어떤 집계 방식으로도
    재현되지 않는다. 이 판정은 파이프라인이 남긴 processed_dataset.parquet가
    있었기 때문에 가능했다 — 덱 자체에는 코드도 중간 산출물도 없다.
    """
    print("\n[C] 원샷 LLM 덱 — 주장 수치 재계산")
    df = pd.read_parquet(OUTPUT_DIR / "processed_dataset.parquet")
    customers = pd.read_csv(DATA_DIR / "olist_customers_dataset.csv")
    items = pd.read_csv(DATA_DIR / "olist_order_items_dataset.csv")
    sellers = pd.read_csv(DATA_DIR / "olist_sellers_dataset.csv")
    payments = pd.read_csv(DATA_DIR / "olist_order_payments_dataset.csv")
    reviews = pd.read_csv(DATA_DIR / "olist_order_reviews_dataset.csv")

    carrier = df["carrier_delivery_time"] / 24
    total = df["total_delivery_time"] / 24
    seller_time = df["seller_processing_time"] / 24
    payment = df["payment_approval_time"] / 24
    delayed = df["delivery_delay"] > 0

    print("  -- 분포 --")
    check.check("C. 원샷", "총 리드타임 평균", 12.62, float(total.mean()), "일")
    check.check("C. 원샷", "총 리드타임 중위", 10.27, float(total.median()), "일")
    check.check("C. 원샷", "Carrier 평균", 9.36, float(carrier.mean()), "일")
    check.check("C. 원샷", "Carrier P90", 18.95, float(carrier.quantile(0.90)), "일")
    check.check("C. 원샷", "Carrier P99", 41.0, float(carrier.quantile(0.99)), "일")
    check.check("C. 원샷", "Carrier 변동계수", 0.94, float(carrier.std() / carrier.mean()))
    check.check("C. 원샷", "Carrier 비중", 74.2, float(carrier.mean() / total.mean() * 100), "%")
    check.check("C. 원샷", "Seller 비중", 22.6, float(seller_time.mean() / total.mean() * 100), "%")
    check.check("C. 원샷", "Payment 비중", 3.2, float(payment.mean() / total.mean() * 100), "%")
    threshold = carrier.quantile(0.90)
    check.check("C. 원샷", "상위 10%가 차지하는 Carrier 시간",
                30.5, float(carrier[carrier >= threshold].sum() / carrier.sum() * 100), "%")
    check.check("C. 원샷", "지연율", 8.2, float(delayed.mean() * 100), "%")
    check.check("C. 원샷", "지연군/정시군 배수",
                3.25, float(carrier[delayed].mean() / carrier[~delayed].mean()), "배")

    print("  -- 지리 --")
    first_item = items.sort_values("order_item_id").drop_duplicates("order_id")
    geo = (df.merge(customers[["customer_id", "customer_state"]], on="customer_id")
             .merge(first_item[["order_id", "seller_id"]], on="order_id")
             .merge(sellers[["seller_id", "seller_state"]], on="seller_id"))
    geo["days"] = geo["carrier_delivery_time"] / 24
    same = geo["customer_state"] == geo["seller_state"]
    a, b = geo.loc[same, "days"].dropna(), geo.loc[~same, "days"].dropna()
    pooled = np.sqrt(((len(a) - 1) * a.var() + (len(b) - 1) * b.var()) / (len(a) + len(b) - 2))
    check.check("C. 원샷", "동일주 배송 건수", 34_181, float(len(a)), "건")
    check.check("C. 원샷", "동일주 평균", 4.82, float(a.mean()), "일")
    check.check("C. 원샷", "타주 평균", 11.91, float(b.mean()), "일")
    check.check("C. 원샷", "Cohen's d", 0.877, float((b.mean() - a.mean()) / pooled))

    share = items.merge(sellers[["seller_id", "seller_state"]], on="seller_id")["seller_state"]
    check.check("C. 원샷", "SP 셀러 아이템 비중",
                71.3, float((share == "SP").mean() * 100), "%")
    check.check("C. 원샷", "SP 셀러 수 비중",
                59.7, float((sellers["seller_state"] == "SP").mean() * 100), "%")

    print("  -- 결제 --")
    pay_type = payments.groupby("order_id")["payment_type"].first()
    by_type = df.merge(pay_type, on="order_id", how="left").groupby("payment_type")["payment_approval_time"].mean()
    check.check("C. 원샷", "Boleto 승인 시간", 32.2, float(by_type["boleto"]), "h")
    check.check("C. 원샷", "신용카드 승인 시간", 3.9, float(by_type["credit_card"]), "h")

    print("  -- 리뷰 (여기서 불일치가 발생한다) --")
    aggregations: Dict[str, Callable[[], pd.Series]] = {
        "평균": lambda: reviews.groupby("order_id")["review_score"].mean(),
        "최저": lambda: reviews.groupby("order_id")["review_score"].min(),
        "첫 리뷰": lambda: reviews.sort_values("review_creation_date")
                          .drop_duplicates("order_id", keep="first")
                          .set_index("order_id")["review_score"],
        "마지막 리뷰": lambda: reviews.sort_values("review_creation_date")
                              .drop_duplicates("order_id", keep="last")
                              .set_index("order_id")["review_score"],
    }
    print("     집계 방식별 '지연 시 1-2점 비율' (덱 주장: 56.7%)")
    for label, fn in aggregations.items():
        joined = df[["order_id", "delivery_delay"]].join(fn().rename("score"), on="order_id").dropna()
        is_delayed = joined["delivery_delay"] > 0
        rate = (joined.loc[is_delayed, "score"] <= 2).mean() * 100
        print(f"       {label:<12} {rate:>6.2f}%")

    score = reviews.groupby("order_id")["review_score"].mean()
    joined = df[["order_id", "delivery_delay"]].join(score.rename("score"), on="order_id").dropna()
    is_delayed = joined["delivery_delay"] > 0
    check.check("C. 원샷", "지연 시 1-2점 리뷰 비율",
                56.7, float((joined.loc[is_delayed, "score"] <= 2).mean() * 100), "%")
    check.check("C. 원샷", "정시 시 1-2점 리뷰 비율",
                9.4, float((joined.loc[~is_delayed, "score"] <= 2).mean() * 100), "%")
    check.check("C. 원샷", "평균 평점", 4.138, float(joined["score"].mean()), "점")
    check.check("C. 원샷", "전체 1-2점 비율",
                13.34, float((joined["score"] <= 2).mean() * 100), "%")


def main() -> None:
    check = Checker()
    verify_notebook_double_join(check)
    verify_untouched_variables(check)
    verify_oneshot_deck(check)
    check.summary()
    print("\n결론: 세 방식의 판정을 가능하게 한 것은 파이프라인이 남긴")
    print("      agent/outputs/processed_dataset.parquet 하나뿐이다.")


if __name__ == "__main__":
    main()
