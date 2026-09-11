# Olist 이커머스 데이터셋 문서

브라질 이커머스 플랫폼 Olist의 주문, 고객, 상품, 판매자, 결제, 리뷰 데이터를 담은 데이터셋입니다.

## olist_customers_dataset
고객의 식별 정보와 지역(위치) 정보를 담은 고객 마스터 테이블입니다.

- **customer_id**: 주문 건별로 부여되는 고객 식별자(1회성 키). 주문 테이블과의 조인 키로 사용됨.
- **customer_unique_id**: 실제 고객 개인을 식별하는 고유 ID. 동일 고객이 여러 번 주문 시 customer_id는 달라도 이 값은 동일함(재구매 분석에 활용).
- **customer_zip_code_prefix**: 고객 우편번호 앞자리 (지역 단위 분석용).
- **customer_city / customer_state**: 고객의 거주 도시/주(state) 카테고리 값.

## olist_geolocation_dataset
우편번호 앞자리 기준의 위도/경도 및 행정구역 정보를 담은 지리 정보 테이블.

- **geolocation_zip_code_prefix**: 우편번호 앞자리 (고객/판매자 zip_code_prefix와 매핑 가능).
- **geolocation_lat / geolocation_lng**: 해당 우편번호 지역의 위도/경도 좌표.
- **geolocation_city / geolocation_state**: 도시/주 카테고리 값.

## olist_orders_dataset
주문의 생명주기(구매~배송완료)를 추적하는 핵심 팩트 테이블.

- **order_id**: 주문 고유 식별자.
- **customer_id**: 주문을 발생시킨 고객 식별자.
- **order_status**: 주문 상태 카테고리(예: delivered, shipped, canceled 등).
- **order_purchase_timestamp**: 고객이 주문을 생성(결제 시작)한 시각.
- **order_approved_at**: 결제 승인 시각.
- **order_delivered_carrier_date**: 물류업체에 상품이 인계된 시각.
- **order_delivered_customer_date**: 고객에게 실제 배송 완료된 시각.
- **order_estimated_delivery_date**: 예상 배송 완료일(고객에게 안내된 기준일, 배송 지연 분석의 기준값).

## olist_order_items_dataset
주문에 포함된 개별 상품 라인아이템(주문-상품-판매자 단위) 정보.

- **order_id**: 소속 주문 식별자.
- **order_item_id**: 한 주문 내 아이템 순번(동일 주문에 여러 상품 존재 가능).
- **product_id**: 주문된 상품 식별자.
- **seller_id**: 해당 아이템을 판매한 판매자 식별자.
- **shipping_limit_date**: 판매자가 물류사에 상품을 인계해야 하는 마감 시각.
- **price**: 상품 판매가.
- **freight_value**: 배송비.

## olist_order_payments_dataset
주문에 대한 결제 수단 및 금액 정보.

- **order_id**: 결제가 이루어진 주문 식별자.
- **payment_sequential**: 한 주문에 여러 결제 수단이 사용된 경우의 순번.
- **payment_type**: 결제 수단 카테고리(예: credit_card, boleto, voucher 등).
- **payment_installments**: 할부 개월 수.
- **payment_value**: 결제 금액.

## olist_order_reviews_dataset
주문에 대한 고객 리뷰(평점 및 코멘트) 정보.

- **review_id**: 리뷰 고유 식별자.
- **order_id**: 리뷰가 작성된 대상 주문.
- **review_score**: 평점(1~5점 카테고리성 수치).
- **review_comment_title / review_comment_message**: 리뷰 제목/본문 텍스트(결측 많음).
- **review_creation_date**: 리뷰 요청/생성 시각.
- **review_answer_timestamp**: 고객이 실제 리뷰를 작성/응답한 시각.

## olist_products_dataset
상품의 속성(카테고리, 크기, 무게 등) 정보를 담은 상품 마스터 테이블.

- **product_id**: 상품 고유 식별자.
- **product_category_name**: 상품 카테고리명(포르투갈어 원문 카테고리).
- **product_name_lenght / product_description_lenght**: 상품명/설명 글자 수.
- **product_photos_qty**: 상품 등록 사진 개수.
- **product_weight_g / product_length_cm / product_height_cm / product_width_cm**: 상품 물리적 규격(배송비 산정 등에 활용).

## olist_sellers_dataset
판매자(셀러)의 식별 및 지역 정보를 담은 판매자 마스터 테이블.

- **seller_id**: 판매자 고유 식별자.
- **seller_zip_code_prefix**: 판매자 우편번호 앞자리.
- **seller_city / seller_state**: 판매자 소재 도시/주 카테고리.

## product_category_name_translation
상품 카테고리명을 포르투갈어에서 영어로 매핑하는 코드 테이블.

- **product_category_name**: 포르투갈어 카테고리명(products 테이블과 조인 키).
- **product_category_name_english**: 영어 번역 카테고리명(리포팅/분석용 표준화 값).

---

## 테이블 관계 (Table Relationships)

| 관계 컬럼 | 관련