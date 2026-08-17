## Candidate Features for Carrier Delivery

### Direct Features
- **olist_orders_dataset.order_delivered_carrier_date (month/weekday)**: 배송사 인계 시점의 월/요일에 따라 물류사의 처리량과 배송 소요시간이 달라질 수 있음
- **olist_customers_dataset.customer_state**: 고객 배송지 주(state)가 배송 거리 및 물류 인프라 차이로 배송 소요시간에 직접 영향을 줄 수 있음
- **olist_customers_dataset.customer_zip_code_prefix**: 고객 우편번호 지역이 배송 커버리지/거점 접근성에 따라 배송시간에 직접 영향을 줄 수 있음
- **olist_sellers_dataset.seller_state**: 발송지(판매자) 주가 배송사 경유 경로 및 거리에 직접 영향을 줄 수 있음
- **olist_sellers_dataset.seller_zip_code_prefix**: 판매자 발송 지역이 배송 시작 지점으로서 배송 소요시간에 직접 영향을 줄 수 있음

### Indirect Features
- **olist_orders_dataset.order_purchase_timestamp (month)**: 주문 시점의 계절성(성수기 등)이 물류사 물량 증가로 배송 지연에 간접적 영향을 줄 수 있음
- **olist_order_items_dataset.shipping_limit_date**: 판매자의 발송 마감 준수 여부가 배송사 인계 이후 처리 흐름에 간접적으로 영향을 줄 수 있음
- **olist_products_dataset.product_weight_g**: 상품 무게가 배송사의 운송 방식/속도 결정에 간접적으로 영향을 줄 수 있음
- **olist_products_dataset.product_category_name**: 상품 카테고리별 취급 방식(위험물, 대형화물 등) 차이가 배송시간에 간접적으로 영향을 줄 수 있음
- **olist_orders_dataset.order_estimated_delivery_date (month)**: 예상 배송일의 계절적 패턴이 물류사의 배송 우선순위 배정에 간접적으로 영향을 줄 수 있음