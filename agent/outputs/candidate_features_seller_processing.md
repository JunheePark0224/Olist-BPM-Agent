## Candidate Features for Seller Processing

### Direct Features
- **olist_orders_dataset.order_approved_at (month/day of week/hour)**: KPI 시작 시점의 요일/시간대(주말, 심야 등)에 따라 판매자 처리 착수 속도가 달라질 수 있음
- **olist_order_items_dataset.seller_id**: 판매자별 처리 역량/숙련도 차이가 승인 후 발송까지 소요시간에 직접 영향을 줌
- **olist_sellers_dataset.seller_state / seller_city**: 판매자 소재지에 따른 물류 인프라, 배송사 픽업 스케줄 차이가 발송 소요시간에 영향
- **olist_order_items_dataset.shipping_limit_date**: 판매자에게 부여된 발송 기한으로, 이 기한과 order_approved_at 간 여유시간이 처리 속도에 영향
- **olist_order_items_dataset.order_item_id (아이템 수)**: 한 주문 내 아이템(라인) 수가 많을수록 포장/처리 시간이 늘어날 수 있음

### Indirect Features
- **olist_orders_dataset.order_purchase_timestamp (month/day of week)**: 주문 시점의 계절적 물량 급증(프로모션, 연말 등)이 판매자 처리 적체에 간접적으로 영향
- **olist_products_dataset.product_weight_g / product_length_cm / product_height_cm / product_width_cm**: 상품의 크기·무게가 포장 준비 시간에 간접적으로 영향
- **olist_products_dataset.product_category_name**: 카테고리별 재고/포장 방식 차이가 처리 소요시간에 간접적으로 영향
- **olist_order_payments_dataset.payment_type**: 결제수단(특히 boleto)에 따라 승인 확정까지 지연이 발생해 이후 처리 착수 타이밍에 간접적으로 영향
- **olist_order_payments_dataset.payment_installments**: 할부 결제 건은 결제 확정 프로세스가 복잡해져 판매자 처리 시작 시점에 간접적 영향