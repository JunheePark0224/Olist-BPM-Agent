# Olist 이커머스 데이터셋 문서

브라질 이커머스 플랫폼 Olist의 주문, 고객, 상품, 판매자, 결제, 리뷰 데이터를 포함하는 데이터셋입니다.

## olist_customers_dataset (고객 정보)
고객의 식별 정보와 거주 지역(위치) 정보를 담은 테이블입니다.

- **customer_id**: 주문 단위로 부여되는 고객 식별자로, 주문 테이블과의 조인 키 역할을 함
- **customer_unique_id**: 실제 개인을 식별하는 고유 ID (동일 고객이 여러 customer_id를 가질 수 있음, 재구매 고객 분석에 활용)
- **customer_zip_code_prefix / customer_city / customer_state**: 고객의 배송지 지역 정보로, 지역별 매출/배송 분석에 사용

## olist_geolocation_dataset (우편번호 위치 정보)
우편번호(zip code prefix)와 위도/경도, 도시/주(state)를 매핑한 지리 정보 참조 테이블입니다.

- **geolocation_zip_code_prefix**: 우편번호 앞자리, 고객/판매자 테이블의 zip_code_prefix와 매칭되는 지리 조인 키
- **geolocation_lat / geolocation_lng**: 지도 시각화 및 거리 계산에 활용되는 좌표값
- **geolocation_city / geolocation_state**: 행정구역 단위 정보

## olist_orders_dataset (주문 정보)
플랫폼에서 발생한 개별 주문의 상태와 배송 프로세스 전 과정의 타임스탬프를 기록한 핵심 팩트 테이블입니다.

- **order_id**: 주문을 식별하는 기본 키로, 주문 아이템/결제/리뷰 테이블과 연결되는 핵심 조인 키
- **customer_id**: 주문을 발생시킨 고객 식별자
- **order_status**: 주문 처리 단계 (delivered, shipped, canceled 등) 카테고리 값으로 주문 퍼널 분석에 사용
- **order_purchase_timestamp**: 고객이 주문을 생성한 시점 (매출 트렌드 분석의 기준 시점)
- **order_approved_at**: 결제 승인 시점
- **order_delivered_carrier_date**: 판매자가 배송사에 상품을 인계한 시점
- **order_delivered_customer_date**: 고객에게 실제 배송 완료된 시점 (배송 리드타임 계산에 사용)
- **order_estimated_delivery_date**: 플랫폼이 고객에게 안내한 예상 배송일 (실배송일과 비교하여 배송 지연 여부 판단)

## olist_order_items_dataset (주문 상세 아이템)
하나의 주문에 포함된 개별 상품 라인아이템 정보로, 상품별 가격과 배송비를 기록한 테이블입니다.

- **order_id**: 상위 주문을 참조하는 외래 키
- **order_item_id**: 동일 주문 내 아이템 순번 (한 주문에 여러 상품이 담길 수 있음)
- **product_id**: 주문된 상품 식별자
- **seller_id**: 해당 아이템을 판매한 판매자 식별자
- **shipping_limit_date**: 판매자가 배송사에 상품을 넘겨야 하는 기한 (SLA 관리 지표)
- **price**: 상품 단가 (매출 계산의 기본 단위)
- **freight_value**: 배송비

## olist_order_payments_dataset (결제 정보)
주문에 대한 결제 수단과 결제 금액, 할부 정보를 담은 테이블입니다.

- **order_id**: 결제가 이루어진 주문 참조 키
- **payment_sequential**: 한 주문에 여러 결제수단이 사용된 경우의 순번
- **payment_type**: 결제 수단 카테고리 (credit_card, boleto, voucher 등)
- **payment_installments**: 할부 개월 수
- **payment_value**: 실제 결제된 금액 (매출/환불 분석의 핵심 지표)

## olist_order_reviews_dataset (주문 리뷰)
고객이 주문 경험에 대해 남긴 평점과 후기 텍스트를 담은 테이블로, 고객 만족도 분석에 사용됩니다.

- **review_id**: 리뷰 고유 식별자
- **order_id**: 리뷰가 작성된 대상 주문 참조 키
- **review_score**: 1~5점 평점 (고객 만족도의 핵심 지표)
- **review_comment_title / review_comment_message**: 리뷰 제목 및 본문 텍스트 (텍스트 마이닝/감성분석 대상)
- **review_creation_date**: 리뷰 설문이 고객에게 발송(생성)된 시점
- **review_answer_timestamp**: 고객이 실제 리뷰를 작성/응답한 시점

## olist_products_dataset (상품 정보)
플랫폼에 등록된 상품의 카테고리 및 물리적 속성(크기, 무게)을 담은 상품 마스터 테이블입니다.

- **product_id**: 상품 고유 식별자
- **product_category_name**: 상품 카테고리명(포르투갈어), 상품군별 매출/트렌드 분석의 기준 축
- **product_name_lenght / product_description_lenght**: 상품명/설명 텍스트 길이 (상품 정보 충실도 지표)
- **product_photos_qty**: 등록된 상