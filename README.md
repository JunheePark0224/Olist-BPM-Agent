# Olist Business Process Optimization Pipeline

Olist 이커머스 배송 데이터에서 병목을 찾고, 원인을 검증하고, **실행 가능한
실험 설계까지** 이어지는 분석 파이프라인. 같은 분석을 세 번 — 수동 노트북,
이 파이프라인, 원샷 LLM — 해보고 결과를 교차 검증한 기록이다.

```
① Data Understanding → ② Preprocessing → ③ Bottleneck Detection
→ ④ Root Cause Analysis (Human Review) → ⑤ Business Impact
→ ⑥ Scenario Recommendation (Human Approval) → ⑦ Experiment Design
→ ⑧ Report Builder → ⑨ PPT Generator
```

**결과**: Carrier Delivery가 리드타임의 74.2%를 차지하는 병목이고, 고객 지역이
η²=20.19%로 가장 큰 원인이다. RJ주 전담 배차 실험을 주문 단위, 1차 지표
Carrier 소요일수(MDE 1.0일)로 설계하면 **206일에 판단이 선다.** 같은 실험을
지연율로 설계했던 이전 버전은 5.6년이 걸렸다.

---

## 왜 이 프로젝트를 만들었나

### 같은 데이터를 세 번 분석했다

| | 방식 | 산출물 |
|---|---|---|
| **v1** | Jupyter 노트북으로 손 분석 | [`comparison/manual_v3.pptx`](comparison/manual_v3.pptx) |
| **v2** | 이 파이프라인 | [`agent/outputs/executive_report.pptx`](agent/outputs/executive_report.pptx) |
| **v3** | CSV 9개를 단일 프롬프트로 LLM에 던짐 | [`comparison/oneshot_llm.pptx`](comparison/oneshot_llm.pptx) |

세 결과를 원본 데이터로 다시 계산해 무엇이 맞고 틀렸는지 확인했다.
전체 기록은 **[docs/verification.md](docs/verification.md)**, 재현은 한 줄이다:

```bash
python scripts/verify_three_way.py
```

| 검증 | 결과 |
|---|---|
| **v1 수동 노트북** | `order_items`를 두 번 조인해 108,581행이 151,581행으로 복제. `product_category` η²가 실제 8.35%인데 **12.77%로 부풀려짐**. 덱의 헤드라인 숫자가 틀려 있었다 |
| **대조군** | 조인을 거치지 않는 변수 3개는 노트북과 파이프라인이 **소수점까지 일치** → 불일치의 원인이 조인임이 확정 |
| **v3 원샷 LLM** | 주장 수치 24개 중 **21개가 정확**하고 파이프라인의 η²를 독립적으로 재확인. 그러나 리뷰 관련 3개는 6가지 집계 어느 것으로도 재현되지 않으며, 그중 하나는 Executive Summary의 근거 |

### 원샷 LLM이 못 하는 것은 분석이 아니라 검증이다

이 프로젝트를 만들기 전, "CSV를 주고 Executive Report PPT를 만들어달라"는
단일 프롬프트로 같은 데이터를 분석시켜봤다. 결과는 놀랍도록 정교했다 —
거리(Haversine) 기반 반응곡선, ΔR² 블록 투입, ICC/Design Effect를 고려한
클러스터 표본 계산까지 수행했고, 분석 깊이는 세 산출물 중 가장 뛰어났다.

그런데 그 결과물을 보고 나서도, 이걸 그대로 남에게 설득할 자신이 없었다.
왜 그 숫자가 그렇게 나왔는지 스스로 확인할 방법이 없었기 때문이다.

그 감각은 맞았다. 덱에는 코드도, 중간 산출물도, 어떤 집계 규칙을 썼는지에
대한 기록도 없다. 리뷰 관련 값 3개가 틀려 있었지만 **읽어서는 찾을 수 없다.**
찾을 수 있었던 것은 이 파이프라인이 `processed_dataset.parquet`를 남겨두었기
때문이고, 같은 파일로 내 손 분석의 조인 버그도 잡았다.

**원샷 LLM은 더 깊은 분석을 더 빨리 낸다. 그런데 그 안의 틀린 숫자를
찾으려면 감사 가능한 파이프라인이 필요했다.** 모델이 더 좋아져도 감사
가능성은 공짜로 생기지 않는다. 이것이 이 프로젝트의 핵심 주장이다.

### 판단과 계산을 파일 단위로 분리했다

LLM과 Python의 역할을 나눴다.
- **LLM**: 후보 변수 제안, 원인 해석 문장, 시나리오 이름 — 판단이 필요한 곳
- **Python**: η²/r² 계산, 조인 경로, 표본 수, 실행 가능성 판정 — 재현 가능해야 하는 곳
- **사람**: 어떤 후보를 승인할지, 처치가 무엇인지, MDE를 얼마로 둘지 —
  `config/*.yaml`에 기록

계산 결과를 사람이 손으로 옮겨 적는 일이 없도록 했다. 이전 버전은
`ab_test_design.yaml` 한 파일에 판단과 계산 결과가 섞여 있었고, 데이터가
바뀌면 숫자가 조용히 낡았다. 지금은 사람이 `experiment_approval.yaml`에
판단만 쓰고, ⑦단계가 `experiment_design_report.json`에 계산을 쓴다.

---

## Human-in-the-loop이 실제로 작동한 사례

설계 원칙은 이론에 머물지 않고 실제로 여러 번 작동했다.

**① 인과가 억지스러운 후보를 사람이 걸렀다.**
④ RCA Step 1에서 LLM이 제안한 후보 변수 중 `product_photos_qty`,
`payment_installments`처럼 인과 관계가 억지스러운 변수를 Human Review에서
제외했다. 기각 사유는 [`approved_features.yaml`](agent/config/approved_features.yaml)에
남아 있다.

**② 검증되지 않은 가정은 자동화하지 않았다.**
노트북이 했던 "배송시간 단축 → 지연율 감소" 시뮬레이션이 검증되지 않은
가정에 기반한다는 것을 발견하고, ⑤단계에서 이 계산을 의도적으로 제외했다.
원샷 LLM 덱은 같은 시뮬레이션을 수행하고 "과대추정일 수 있다"고 각주로
인정하면서도 그 값을 헤드라인으로 썼다. 이 판단은 옳았다.

**③ 실험이 실행 불가능하다는 것을 발견하고, 설계를 바꿔 실행 가능하게 만들었다.**
A/B Test를 설계해보니 필요 표본 대비 트래픽이 부족해 **5.6년**이 걸렸다
(지연율 −1.0%p, α=0.05 양측, power 0.80 → arm당 17,866건, RJ 하루 17.6건 기준 2,030일).
원인은 1차 지표를 지연율(이진값)로 둔 것이었다. 이진 지표는 약속일 경계를
넘나드는 주문만 값이 변해 정보를 대부분 버린다. 지표를 Carrier 소요일수
(연속형)로 바꾸고 상대 개선폭을 동등하게(8.3% vs 7.4%) 유지하니 **206일**이
됐다 — 목표를 낮춘 것이 아니라 측정 방식을 바꾼 것이다.

이 발견을 일회성으로 두지 않고 규칙으로 만들었다. ⑦단계는
`max_duration_days`를 넘으면 `infeasible`로 판정하고 대안을 계산해
제시하되, **MDE 완화보다 지표 유형 변경을 먼저 권한다.** 기간이 더 짧게
나오더라도 목표를 낮추는 쪽을 먼저 추천하면 안 되기 때문이다.

**④ 실험 단위는 데이터가 아니라 처치가 결정한다는 것을 명시했다.**
이전 설계는 실험 단위를 "물류 거점"으로 선언하면서 개별 랜덤화 공식으로
표본을 계산했다. 거점 단위면 Design Effect를 곱해야 하는데, Olist에는
거점 컬럼이 없어 계산 자체가 불가능했다. 지금은 사람이 처치("RJ향 주문을
전담 배차로 전환")를 먼저 정하고, 그 처치가 허용하는 단위(주문)를 고르며,
⑦단계가 다른 단위(셀러·우편번호 권역)를 골랐을 때의 ICC·Design Effect·기간을
표로 함께 제시한다. 거점은 `not_evaluable`로 이유와 함께 남는다.

---

## Root Cause Analysis를 설계하는 관점

"무엇이 병목의 원인인가"를 감으로 판단하지 않고 검증 가능한 기준으로
표준화하는 것이 반복적으로 다룬 문제였다.

- **원인 후보 발굴**: LLM이 데이터 딕셔너리와 KPI 정의를 보고 병목 구간과
  직접 관련된 변수(Direct)와 간접 변수(Indirect)를 구분해 제안한다.
- **효과크기 검증**: 범주형은 η²(ANOVA), 연속형은 r²(Pearson)로 실제
  설명력을 계산해 "통계적으로 유의하다"와 "실질적으로 중요하다"를 구분한다.
- **선정 기준의 표준화**: `effect_size_pct >= threshold` 규칙으로, 병목이
  몇 개든 변수가 몇 개든 같은 기준으로 원인을 선별한다.
- **설명력과 비즈니스 임팩트의 분리**: Effect Size(원인이 통계적으로 얼마나
  중요한가)와 Impact Score(개선했을 때 효과가 얼마나 큰가)는 다른 질문이다.
  실제로 Seller Processing의 가장 중요한 원인(Product Category, η²=8.35%)과
  Impact Score가 가장 높은 시나리오(Carnival Season)가 달랐고, 두 지표를
  보고서에 병기했다.
- **해석 문장에 실제 수치를 인용**: ④단계가 그룹 극값을 함께 넘겨
  LLM이 "SP 132.9h → AP 589.5h, 4.4배"처럼 데이터에 있는 값만 쓰게 한다.
  요일·월 같은 파생값은 라벨을 붙여 LLM이 스스로 해석하지 못하게 했다
  (실제로 `dayofweek=0`을 일요일로 읽은 사례가 있었다 — pandas는 월요일).

## 주요 설계 결정

- **규칙 기반 병목 판정**: `min_share_pct`, `min_delay_ratio` 임계값
- **Join Engine**: `data_dictionary.json`의 관계 그래프에서 BFS로 조인 경로를
  도출하고, 이미 조인한 테이블을 집합으로 추적해 재조인을 차단한다.
  노트북의 이중 조인 버그를 이 구조 덕에 잡았다.
  [`tests/test_join_engine.py`](tests/test_join_engine.py)가 이 보장을 실행
  가능한 형태로 못 박는다 — 같은 픽스처에서 노트북 방식은 6행, join_engine은 4행.
- **실행 가능성의 규칙화**: `experiment_policy.max_duration_days`
- **판단/계산의 파일 분리**: `experiment_approval.yaml` / `experiment_design_report.json`
- **LLM 산출물의 검증 범위 명시**: 피쉬본 다이어그램의 세부 원인은 LLM이
  도메인 지식으로 생성한 가설이며 검증되지 않았음을 슬라이드 각주에 밝힌다.
  인과 판단이 필요한 산출물은 자동화 대상에서 제외한다는 원칙과 같은 논리다.
- **MCP 서버 연동**: Claude Desktop에서 단계별 tool로 실행, Human
  Review/Approval 지점에서 대기

---

## 실행 방법

### 설치
```bash
pip install -r requirements.txt
```
`graphviz`는 Python 바인딩 외에 시스템 실행 파일이 필요하다
(https://graphviz.org/download/ — PATH 등록). 없으면 ④단계가 다이어그램만
건너뛰고 계속 진행한다. LLM을 호출하는 ①④⑥은 `ANTHROPIC_API_KEY`가 필요하다.

### 전체 실행
```bash
cd agent/src
python main.py
```
④ 뒤와 ⑥ 뒤에 멈춘다. `approved_features.yaml`, `experiment_approval.yaml`을
확인하고 Enter.

### LLM 없이 재현 (⑦⑧⑨)
```bash
cd agent/src
python -c "import experiment_design, report_builder, ppt_generator; experiment_design.run(); report_builder.run(); ppt_generator.run('../outputs/report_data.json','../outputs/executive_report.pptx','../outputs')"
```
커밋된 산출물 JSON만 읽으므로 API 키 없이 몇 초 만에 덱이 만들어진다.

### 검증
```bash
python scripts/verify_three_way.py   # 세 방식 교차 검증 재현
pytest tests/                        # join_engine 보장
```

### 대화형 실행 (Claude Desktop + MCP)
`claude_desktop_config.json`에 `agent/src/server.py`를 등록하면 단계별
tool로 실행할 수 있다. ⑦은 실행 가능성 판정을 반환하므로, `infeasible`이면
대화 중에 대안을 확인하고 `experiment_approval.yaml`을 고쳐 다시 호출하는
흐름이 된다.

## 폴더 구조

```
agent/
├── config/       # Human Input — kpi_definition, preprocessing_policy,
│                 #   approved_features, experiment_approval
├── src/          # 파이프라인 모듈 9개 + join_engine, labels, MCP 서버
└── outputs/      # 실행 산출물 (JSON, PNG, PPTX)
comparison/       # 대조군 — 수동 분석 덱, 원샷 LLM 덱
docs/             # verification.md — 세 방식 교차 검증
scripts/          # verify_three_way.py — 검증 재현
tests/            # join_engine 테스트
notebooks/        # v1 수동 분석 (Jupyter)
data/             # Olist 원본 CSV (포함 이유는 data/README.md)
```

## 기술 스택

Python, pandas, scipy, matplotlib, graphviz, python-pptx, pytest,
Anthropic Claude API, MCP (Model Context Protocol)

## 한계

**다른 데이터셋에서 검증되지 않았다.** 데이터셋 종속 값(컬럼명, 파일명, 단위)은
전부 `kpi_definition.yaml`과 `approved_features.yaml`에 있어 코드 수정 없이
교체할 수 있게 했지만, 실제로 해본 적은 없다.

설정으로 풀리지 않는 구조적 가정 두 가지는 명시해둔다:
1. **KPI가 "구간 소요시간"이다.** `processes`의 start→end 차이로 계산되는
   시간형 지표를 전제한다. 전환율이나 매출 같은 KPI면 ②③⑤⑦을 재설계해야 한다.
2. **분석 단위가 단일 테이블 grain이다.** base_table 1행 = 분석 1건.
   세션·이벤트처럼 다대다 구조는 맞지 않는다.

**LLM 산출물은 실행마다 달라진다.** 시나리오 제목, 해석 문장, 피쉬본 세부
원인은 재실행 시 바뀐다. 파이프라인은 id와 계산값으로 연결되어 깨지지
않지만, 문장 수준의 재현성은 없다.

**피쉬본의 세부 원인은 검증되지 않았다.** 카테고리와 η²는 계산값이지만
그 아래 세 줄은 LLM의 가설이다. 슬라이드에 그렇게 명시했다.

## 다음 단계

다른 이커머스 공개 데이터셋에 설정 파일만 바꿔 적용해보고, 병목이 3개
이상이거나 RCA threshold를 통과하는 변수가 없는 경우 같은 엣지 케이스를
찾아 보완하는 것. 그 과정 자체를 두 번째 검증 기록으로 남기는 것.
