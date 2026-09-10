# data/

## 원본

[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (Kaggle, CC BY-NC-SA 4.0)

9개 CSV, 약 120MB. 2016.09–2018.08 브라질 이커머스 주문 약 10만 건.

| 파일 | 행 | 내용 |
|---|---|---|
| `olist_orders_dataset.csv` | 99,441 | 주문 (base table). 구매·승인·집하·배송완료·예상배송 시각 |
| `olist_order_items_dataset.csv` | 112,650 | 주문 아이템. **주문당 여러 행** — 조인 시 행 복제 주의 |
| `olist_customers_dataset.csv` | 99,441 | 고객 주(州), 우편번호 |
| `olist_sellers_dataset.csv` | 3,095 | 셀러 주(州), 우편번호 |
| `olist_products_dataset.csv` | 32,951 | 카테고리, 무게, 치수 |
| `olist_order_reviews_dataset.csv` | 99,224 | 리뷰 평점. 주문당 여러 행 가능 |
| `olist_order_payments_dataset.csv` | 103,886 | 결제 수단 |
| `olist_geolocation_dataset.csv` | 1,000,163 | 우편번호별 좌표 (파이프라인 미사용, 59MB) |
| `product_category_name_translation.csv` | 71 | 카테고리 포르투갈어→영어 |

## 저장소에 포함한 이유

원본 CSV를 커밋한 것은 관례에 어긋난다. 그럼에도 포함한 이유는
[`docs/verification.md`](../docs/verification.md)의 모든 수치를
`python scripts/verify_three_way.py` 한 줄로 재현할 수 있게 하기 위해서다.
검증 가능성이 이 프로젝트의 핵심 주장이므로, 그 검증에 필요한 입력을
별도 다운로드 없이 제공한다.

## `archive/orders_delivered_clean.csv`

수동 노트북(`notebooks/01_Preprocessing.ipynb`)이 만든 전처리 결과.
파이프라인은 이 파일을 쓰지 않고 `agent/outputs/processed_dataset.parquet`를
직접 만든다. `verify_three_way.py`가 노트북의 이중 조인 버그를 재현할 때
노트북과 동일한 입력을 쓰기 위해 보관한다.
