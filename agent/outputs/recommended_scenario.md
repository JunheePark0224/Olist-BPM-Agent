# Recommended Improvement Scenarios

## S1. RJ Carrier Delivery Time Reduction

**Variable:** customer_state
**Included Values:** customer_state=RJ
**Effect Size:** 20.19%
**Impact Score:** 788,027

**Reason:** RJ has the highest impact score among all states, driven by large order volume and significant excess delivery hours. Other states like BA and RS represent distinct regional logistics issues, not part of the same event.

**Expected Effect:** Optimizing carrier logistics for RJ could reduce delivery time by approximately 20% and save the most cumulative delivery hours across the network.

---

## S2. Office Furniture Processing Time Improvement

**Variable:** product_category_name_english
**Included Values:** product_category_name_english=office_furniture
**Effect Size:** 8.35%
**Impact Score:** 295,903

**Reason:** Office furniture shows by far the highest impact score and excess processing hours among product categories. Other categories like furniture_decor and computers_accessories represent unrelated product lines with much lower impact.

**Expected Effect:** Streamlining seller processing workflows for office furniture could reduce processing time by about 8.35% and significantly cut excess handling hours.

---

## S3. Carnival Season Carrier Delay Mitigation

**Variable:** carrier_month
**Included Values:** carrier_month=3.0, carrier_month=2.0
**Effect Size:** 5.77%
**Impact Score:** 1,311,657

**Reason:** February and March together correspond to Brazil's Carnival season, when logistics and carrier operations are commonly disrupted. Combining these reflects a single seasonal business event rather than two independent months.

**Expected Effect:** Proactive carrier scheduling around Carnival season could cut delivery delays by roughly 5.8% and prevent excess hours during this recurring seasonal disruption.

---

## S4. End-of-Week Seller Processing Delay Reduction

**Variable:** seller_dayofweek
**Included Values:** seller_dayofweek=4.0, seller_dayofweek=5.0
**Effect Size:** 2.45%
**Impact Score:** 519,915

**Reason:** Thursday and Friday both show elevated seller processing times, reflecting a common end-of-week bottleneck before the weekend. Wednesday's impact is negligible and does not fit this pattern, so it is excluded.

**Expected Effect:** Improving seller processing capacity on Thursdays and Fridays could reduce processing delays by about 2.45% and prevent weekend order backlog.

---
