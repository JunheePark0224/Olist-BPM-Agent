## Candidate Features for Carrier Delivery

### Direct Features
- **olist_orders.order_delivered_carrier_date (month/day_of_week)**: 이 KPI의 시작 시점으로, 배송 시작 시기의 계절성/요일성(연휴, 성수기 등)이 배송 소요시간에 직접 영향을 줄 수 있음
- **olist_customers_dataset.customer_state**: 배송 도착지(주) 정보로, 물류사 배송 커버리지 및 거리 차이에 따라 소요시간에 직접적 영향을 줌
- **olist_customers_dataset.customer_zip_code_prefix**: 고객 지역 세분화 정보로, 배송 권역별 소요시간 차이를 직접 반영할 수 있음
- **olist_sellers_dataset.seller_state**: 배송 출발지(주) 정보로, 판매자-고객 간 물류 이동 경로 특성에 직접 영향을 줌
- **olist_sellers_dataset.seller_zip_code_prefix**: 판매자 지역 세분화 정보로, 출고지 위치가 배송 경로 및 소요시간에 직접적으로 관여함

### Indirect Features
- **olist_orders_dataset.order_purchase_timestamp (month/day_of_week)**: 주문 시점의 계절적 물량 변동(성수기 등)이 이후 물류사 처리 용량에 간접적으로 영향을 줄 수 있음
- **olist_products_dataset.product_weight_g**: 상품 무게가 무거울수록 운송 및 취급 시간이 길어져 간접적으로 배송 소요시간에 영향을 줄 수 있음
- **olist_products_dataset.product_length_cm / product_height_cm / product_width_cm**: 상품 부피가 클수록 운송 효율이 낮아져 배송 소요시간에 간접적 영향을 줄 수 있음
- **olist_products_dataset.product_category_name**: 상품 카테고리에 따라 취급 난이도(파손주의, 특수배송 등)가 달라 배송 소요시간에 간접적 영향을 줄 수 있음
- **olist_order_items_dataset.shipping_limit_date (month/day_of_week)**: 판매자의 발송 마감 시점 패턴이 물류사 인계 및 이후 배송 처리 흐름에 간접적으로 영향을 줄 수 있음