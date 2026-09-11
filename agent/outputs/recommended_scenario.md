# Recommended Improvement Scenarios

## S1. RJ Delivery Optimization

**Variable:** customer_state
**Included Values:** customer_state=RJ
**Effect Size:** 20.19%
**Impact Score:** 788,027

**Reason:** RJ has the highest impact score among states with comparable effect size, driven by high order volume and significant excess hours. Other states like BA and RS represent separate regional issues, not a shared event.

**Expected Effect:** Reducing carrier delivery delays in RJ could recover the largest single regional impact on delivery time KPI.

---

## S2. Office Furniture Processing Time Reduction

**Variable:** product_category_name_english
**Included Values:** product_category_name_english=office_furniture
**Effect Size:** 8.35%
**Impact Score:** 295,903

**Reason:** Office furniture shows by far the largest excess processing hours and impact score among product categories. Other categories like furniture_decor and computers_accessories reflect unrelated product handling issues.

**Expected Effect:** Streamlining seller processing for bulky office furniture items could substantially cut fulfillment delays.

---

## S3. Carnival Season Carrier Delay Mitigation

**Variable:** carrier_month
**Included Values:** carrier_month=3.0, carrier_month=2.0
**Effect Size:** 5.77%
**Impact Score:** 1,311,657

**Reason:** February and March align with Brazil's Carnival season, a known period of nationwide logistics disruption and courier slowdowns. December, while also high impact, reflects a distinct holiday-driven event and is excluded.

**Expected Effect:** Proactive carrier capacity planning around Carnival could significantly cut excess delivery hours during this seasonal peak.

---

## S4. Pre-Weekend Seller Processing Slowdown Fix

**Variable:** seller_dayofweek
**Included Values:** seller_dayofweek=4.0, seller_dayofweek=5.0
**Effect Size:** 2.45%
**Impact Score:** 519,915

**Reason:** Thursday and Friday show similarly elevated excess processing hours, suggesting a shared pre-weekend slowdown pattern in seller order handling. Wednesday's excess hours are negligible, indicating it is not part of this pattern.

**Expected Effect:** Improving seller throughput on Thursdays and Fridays could prevent weekend-driven processing backlogs.

---
