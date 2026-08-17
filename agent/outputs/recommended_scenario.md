# Recommended Improvement Scenarios

## S1. RJ Carrier Delivery Speed-up

**Variable:** customer_state
**Included Values:** customer_state=RJ
**Effect Size:** 20.19%
**Impact Score:** 788,027

**Reason:** RJ shows the highest impact score among all state-level delivery delays, driven by a large order volume combined with significant excess delivery hours. No other state shares a common root cause to justify grouping.

**Expected Effect:** Reducing carrier delivery time in RJ could cut excess delivery hours by up to 20% for over 12,000 orders.

---

## S2. Office Furniture Processing Time Reduction

**Variable:** product_category_name_english
**Included Values:** product_category_name_english=office_furniture
**Effect Size:** 8.35%
**Impact Score:** 295,903

**Reason:** Office furniture shows by far the highest seller processing time impact, distinct from other categories with no shared operational cause. It stands out as the single most impactful category to address.

**Expected Effect:** Streamlining seller processing for office furniture could reduce processing time by about 8.35% for 1,659 orders.

---

## S3. Carnival Season Carrier Delay Mitigation

**Variable:** carrier_month
**Included Values:** carrier_month=2.0, carrier_month=3.0
**Effect Size:** 5.77%
**Impact Score:** 1,311,657

**Reason:** February and March correspond to Brazil's Carnival season, which causes widespread logistics slowdowns nationwide, justifying their combination. Together they represent the largest impact among all monthly patterns.

**Expected Effect:** Proactive carrier capacity planning during Carnival could reduce delivery delays by roughly 5.8% across nearly 17,700 orders.

---

## S4. End-of-Week Seller Processing Bottleneck

**Variable:** seller_dayofweek
**Included Values:** seller_dayofweek=4.0, seller_dayofweek=5.0
**Effect Size:** 2.45%
**Impact Score:** 519,915

**Reason:** Thursday and Friday represent consecutive end-of-week days where seller processing backlogs accumulate before the weekend, forming a coherent business pattern. Together they have the largest combined impact among weekday groups.

**Expected Effect:** Improving seller workflow efficiency on Thursdays and Fridays could cut processing delays by about 2.45% for over 25,900 orders.

---
