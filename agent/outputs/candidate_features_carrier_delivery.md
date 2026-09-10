## Candidate Features for Carrier Delivery

### Direct Features
- **olist_orders_dataset.order_delivered_carrier_date (month/dayofweek)**: 배송사 인계 시점의 월/요일에 따른 물류량, 주말 인계 여부 등이 배송 소요시간에 직접 영향을 줄 수 있음
- **olist_customers_dataset.customer_state**: 배송 도착지(고객) 지역에 따라 배송사 이동 거리와 인프라 차이로 소요시간이 달라짐
- **olist_customers_dataset.customer_city**: 고객이 위치한 도시(대도시 vs 지방)에 따라 배송 인프라 및 소요시간 차이 발생
- **olist_sellers_dataset.seller_state**: 판매자 발송 지역에 따라 배송사 경유 거점 및 이동 거리가 달라져 소요시간에 영향
- **olist_orders_dataset.order_estimated_delivery_date**: 예상 배송일과 실제 인계 시점의 간격이 배송사의 처리 우선순위에 간접 영향을 줄 수 있음

### Indirect Features
- **olist_orders_dataset.order_purchase_timestamp (month/dayofweek)**: 주문 시점의 계절성(연말 성수기 등)이 이후 배송사 처리 물량 증가로 이어져 배송 시간에 간접 영향
- **olist_order_items_dataset.shipping_limit_date**: 판매자 발송 기한 준수 여부가 배송사 인계 지연 및 이후 배송 프로세스에 영향
- **olist_products_dataset.product_weight_g**: 상품 무게가 무거울수록 배송사 운송/분류 처리 시간이 길어질 수 있음
- **olist_products_dataset.product_category_name**: 상품 카테고리에 따라 특수 취급(대형가구, 가전 등) 여부로 배송 소요시간 차이 발생
- **olist_order_items_dataset.freight_value**: 배송비 수준이 배송 방식(특송/일반)이나 운송 경로 차이를 반영해 소요시간에 간접적 영향