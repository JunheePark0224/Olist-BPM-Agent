# Olist 이커머스 데이터셋 설명 문서

## olist_customers_dataset
고객의 식별 정보와 지역(위치) 정보를 담은 테이블입니다.

- **customer_id**: 주문 건별로 부여되는 고객 식별자(주문 단위 키, `olist_orders_dataset`과 조인에 사용).
- **customer_unique_id**: 동일 고객을 여러 주문에 걸쳐 식별하기 위한 고유 ID (재구매 고객 분석에 활용).
- **customer_zip_code_prefix / customer_city / customer_state**: 고객의 배송지 우편번호·도시·주 정보로, 지역 기반 매출·배송 분석에 사용.

## olist_geolocation_dataset
우편번호(prefix) 기준 위도/경도 및 도시·주 정보를 담은 위치 마스터 테이블입니다.

- **geolocation_zip_code_prefix**: 우편번호 앞자리 (고객/판매자 테이블의 zip_code_prefix와 연결 가능한 지리 정보 키).
- **geolocation_lat / geolocation_lng**: 해당 우편번호 지역의 위도·경도 (지도 시각화, 배송 거리 계산에 활용).
- **geolocation_city / geolocation_state**: 도시명·주 코드.

## olist_orders_dataset
주문의 생명주기(발주~배송완료)를 추적하는 핵심 팩트 테이블입니다.

- **order_id**: 주문 고유 식별자 (다른 주문 관련 테이블들과의 연결 키).
- **customer_id**: 주문을 발생시킨 고객 식별자.
- **order_status**: 주문 상태(예: delivered, shipped, canceled 등) — 주문 이행 성공/실패 분석에 핵심.
- **order_purchase_timestamp**: 고객이 주문(결제 시작)을 한 시각 — 매출/트래픽 시계열 분석의 기준.
- **order_approved_at**: 결제가 승인된 시각.
- **order_delivered_carrier_date**: 물류사에 상품이 인계된 시각.
- **order_delivered_customer_date**: 고객에게 실제 배송 완료된 시각 — 리드타임 계산에 사용.
- **order_estimated_delivery_date**: 시스템이 예측한 배송 예정일 — 실제 배송일과 비교해 배송 지연율 분석에 활용.

## olist_order_items_dataset
주문에 포함된 개별 상품(라인 아이템) 단위 상세 내역 테이블입니다.

- **order_id**: 상위 주문 식별자.
- **order_item_id**: 한 주문 내에서 아이템의 순번(같은 주문에 여러 상품/수량이 있을 경우 구분).
- **product_id**: 판매된 상품 식별자.
- **seller_id**: 해당 아이템을 판매한 판매자 식별자.
- **shipping_limit_date**: 판매자가 물류사에 상품을 인계해야 하는 마감 시각 — SLA 준수 여부 분석에 사용.
- **price / freight_value**: 상품 가격과 배송비 — 매출 및 수익성 분석의 기본 단위.

## olist_order_payments_dataset
주문에 대한 결제 수단 및 금액 정보를 담은 테이블입니다.

- **order_id**: 결제가 발생한 주문 식별자.
- **payment_sequential**: 한 주문에 여러 결제 수단이 사용된 경우의 순번.
- **payment_type**: 결제 수단(credit_card, boleto, voucher 등) — 결제 채널 분석에 사용.
- **payment_installments**: 할부 개월 수.
- **payment_value**: 결제 금액 — 주문 매출액 산정의 핵심 지표.

## olist_order_reviews_dataset
주문 완료 후 고객이 남긴 리뷰(평점 및 코멘트) 데이터를 담은 테이블입니다.

- **review_id**: 리뷰 고유 식별자.
- **order_id**: 리뷰가 작성된 대상 주문.
- **review_score**: 1~5점 평점 — 고객 만족도(CSAT) 지표.
- **review_comment_title / review_comment_message**: 리뷰 제목·본문 텍스트 — 정성적 VOC 분석, 텍스트 마이닝에 활용.
- **review_creation_date**: 리뷰가 시스템에 생성(요청)된 시각.
- **review_answer_timestamp**: 고객이 실제로 리뷰를 응답(작성 완료)한 시각.

## olist_products_dataset
상품 마스터 정보를 담은 테이블입니다.

- **product_id**: 상품 고유 식별자.
- **product_category_name**: 상품 카테고리명(포르투갈어) — 카테고리별 매출/판매량 분석의 기준 축.
- **product_name_lenght / product_description_lenght**: 상품명·설명 글자 수 — 상품 정보 품질 분석에 활용.
- **product_photos_qty**: 등록된 상품 사진 수 — 상품 노출/전환율과의 상관관계 분석에 사용.
- **product_weight_g / product_length_cm / product_height_cm / product_width_cm**: 상품 물리적 규격(무게·크기) — 배송비 산정 및 물류 최적화에 활용.

## olist_sellers_dataset
판매자(셀러)의 식별 정보와 소재지 정보를 담은 테이블입니다.

- **seller_id**: 판매자 고유 식별자.
- **seller_zip_code