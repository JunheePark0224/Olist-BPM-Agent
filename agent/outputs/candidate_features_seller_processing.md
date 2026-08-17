## Candidate Features for Seller Processing

### Direct Features
- **olist_orders_dataset.order_approved_at (month/weekday/hour)**: KPI 시작 시점의 계절성·요일·시간대(예: 주말/야간 승인 여부)가 판매자 처리 착수 시점에 직접 영향을 줄 수 있음
- **olist_order_items_dataset.shipping_limit_date**: 판매자가 지켜야 하는 처리 마감 기한으로, order_approved_at 대비 여유 기간이 실제 발송 소요시간에 직접적 제약을 줌
- **olist_sellers_dataset.seller_state**: 판매자가 위치한 지역(주)에 따라 물류사 픽업 빈도나 창고 운영 방식이 달라 처리 소요시간에 직접 영향
- **olist_sellers_dataset.seller_city**: 판매자 소재 도시 규모(대도시/지방)에 따라 물류 인프라 접근성이 달라 발송 처리 속도에 영향
- **olist_order_items_dataset.order_item_id (주문 내 아이템 수, count)**: 한 주문에 포함된 아이템 수가 많을수록 포장·집하 준비 시간이 길어질 수 있음

### Indirect Features
- **olist_orders_dataset.order_purchase_timestamp (month/weekday)**: 주문 발생 시점의 계절적 성수기 여부가 판매자의 재고·주문 처리량 부담에 간접적으로 영향
- **olist_products_dataset.product_category_name**: 상품 카테고리별로 판매자의 재고 준비·포장 방식이 달라 처리 시간에 간접 영향
- **olist_products_dataset.product_weight_g / product_length_cm / product_height_cm / product_width_cm**: 상품의 물리적 크기·무게가 포장 및 발송 준비 난이도에 간접적으로 영향
- **olist_order_payments_dataset.payment_type**: 결제 수단(특히 boleto 등 승인 지연 가능성이 있는 방식)에 따라 이후 처리 프로세스 착수 타이밍이 간접적으로 달라질 수 있음
- **olist_order_items_dataset.freight_value**: 배송비 수준이 판매자가 이용하는 물류사·배송 방식 선택에 영향을 주어 간접적으로 처리 속도에 반영될 수 있음