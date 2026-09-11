## Candidate Features for Seller Processing

### Direct Features
- **olist_orders_dataset.order_approved_at (month/dayofweek/hour)**: KPI 시작 시점의 요일·시간대에 따라 판매자의 처리 착수 속도가 달라질 수 있음
- **olist_order_items_dataset.shipping_limit_date**: 판매자에게 부여된 발송 마감 기한으로, 이 기한과 승인 시각 간 간격이 실제 처리 소요시간에 직접적 제약을 줌
- **olist_sellers_dataset.seller_state**: 판매자 소재 주(state)에 따라 물류 인프라 접근성이 달라 발송 처리 속도에 영향을 줄 수 있음
- **olist_sellers_dataset.seller_city**: 판매자 소재 도시의 물류 인프라 수준이 처리 속도에 직접 영향을 줄 수 있음
- **olist_order_items_dataset.order_item_id (count/max)**: 한 주문에 포함된 아이템 수가 많을수록 포장/처리 시간이 늘어날 수 있음

### Indirect Features
- **olist_orders_dataset.order_purchase_timestamp (month/dayofweek)**: 주문 발생 시점의 계절적 물량 변동(성수기 등)이 판매자 처리 지연에 간접적으로 영향을 줄 수 있음
- **olist_products_dataset.product_weight_g / product_length_cm / product_height_cm / product_width_cm**: 상품의 물리적 크기와 무게가 포장 및 발송 준비 시간에 간접적으로 영향을 줄 수 있음
- **olist_products_dataset.product_category_name**: 상품 카테고리에 따라 처리 프로세스(포장 난이도, 재고 위치 등)가 달라 소요시간에 영향을 줄 수 있음
- **olist_order_payments_dataset.payment_type**: 결제 수단(예: boleto는 승인까지 시차가 있어 간접적으로 처리 흐름에 영향)에 따라 이후 처리 속도가 달라질 수 있음
- **olist_order_payments_dataset.payment_installments**: 할부 개월 수가 많은 고가/특수 주문일수록 처리 절차가 달라질 가능성이 있음