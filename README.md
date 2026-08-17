# Olist Business Process Optimization Agent

Olist 이커머스 배송 데이터를 기반으로, 병목 탐지 → 원인 분석 →
개선 시나리오 추천 → A/B Test 설계 → Executive Report 생성까지
전체 분석 프로세스를 자동화하는 AI Agent 파이프라인.

## 배경

기존에 노트북(Jupyter)으로 수동 진행했던 8단계 데이터 분석 프로세스를
Agent 파이프라인으로 재구현하며, LLM과 Python의 역할을 명확히 분리했다.
- LLM: 후보 제안, 해석, 카테고리 그룹핑처럼 판단이 필요한 영역
- Python: 통계 계산(η²/r²), 규칙 기반 필터링처럼 재현 가능해야 하는 영역

## 프로젝트의 의의

### 왜 "LLM에게 CSV 주고 PPT 만들어줘"로 끝나지 않는가

실제로 이 프로젝트를 만들기 전, "CSV를 주고 Executive Report PPT를
만들어달라"는 단일 프롬프트로 같은 데이터를 분석시켜본 적이 있다.
결과는 놀랍도록 정교했다 — 실제로 코드를 실행해 거리(Haversine)
기반 원인 분석, ICC/Design Effect를 고려한 클러스터 표본 계산까지
수행했고, 핵심 결론(Carrier Delivery가 74.2% 병목, 고객 지역이
20% 내외의 설명력을 가진 핵심 원인)도 이 프로젝트의 결과와 거의
일치했다.

그런데 그 결과물을 보고 나서도, 이걸 그대로 남에게 설득할 자신이
없었다. 복잡한 공식과 지표들이 등장했지만, 왜 그 숫자가 그렇게
나왔는지, 이 판단이 정말 타당한지 스스로 확인할 방법이 없었기
때문이다. 그 경험은 오히려 이 프로젝트가 왜 필요한지를 더 분명하게
만들었다.
**LLM이 정답을 한 번에 만들어내는 것이 아니라, LLM의 판단과
Python의 계산을 분리하고, 사람이 개입할 지점을 구조적으로
만들어 신뢰할 수 있는 분석 프로세스를 설계하는 것**이 이
프로젝트의 핵심 가치다.

### Human-in-the-loop이 실제로 작동한 사례

이 설계 원칙은 이론에 머물지 않고 실제로 여러 번 작동했다.

- ④ RCA Step 1에서 LLM이 제안한 후보 변수 중 `product_photos_qty`,
  `payment_installments`처럼 인과 관계가 억지스러운 변수를
  Human Review 단계에서 제외했다.
- ⑤ Business Impact Simulation을 설계하는 과정에서, 노트북이
  했던 "배송시간 단축 → 지연율 감소" 시뮬레이션이 검증되지 않은
  가정에 기반한다는 것을 발견하고, 이 계산을 자동화 대상에서
  의도적으로 제외했다.
- ⑧ A/B Test Design에서 필요 샘플 수 대비 실제 트래픽을 계산해
  본 결과 "현재 트래픽 기준 실험에 4.5년이 걸린다"는 사실을
  발견했다. 이를 숨기지 않고 `requires_feasibility_review`로
  명시해, 다음 단계(MDE 조정 또는 대상 확대)를 판단할 수 있게
  기록했다.

### Root Cause Analysis를 설계하는 관점

이 프로젝트에서 가장 반복적으로 다룬 문제는 "무엇이 병목의
원인인가"를 사람이 감(직관)으로 판단하지 않고, 검증 가능한
기준으로 표준화하는 것이었다.

- **원인 후보 발굴**: LLM이 데이터 딕셔너리와 KPI 정의를 보고
  "이 병목 구간과 직접 관련된 변수(Direct)"와 "간접적으로 영향을
  줄 수 있는 변수(Indirect)"를 구분해 제안하도록 설계했다.
- **효과크기 검증**: 범주형 변수는 η²(ANOVA), 연속형 변수는
  r²(Pearson)로 실제 설명력을 계산해, "통계적으로 유의하다"는
  것과 "실질적으로 중요하다"는 것을 구분했다.
- **원인 선정 기준의 표준화**: 노트북에서는 "감으로 상위 몇 개를
  골랐는지" 기준이 매번 달랐다. 이 프로젝트에서는
  `effect_size_pct >= threshold`라는 규칙으로 바꿔, 병목이
  몇 개든, 변수가 몇 개든 항상 같은 기준으로 원인을 선별한다.
- **설명력과 비즈니스 임팩트의 분리**: Effect Size(원인이 통계적
  으로 얼마나 중요한가)와 Impact Score(개선했을 때 비즈니스
  효과가 얼마나 큰가)는 다른 질문이라는 것을 설계 단계에서
  명확히 구분했다. 실제로 Seller Processing의 가장 중요한 원인
  (Product Category, η²=8.35%)과 Impact Score가 가장 높은
  시나리오(Carnival Season, 계절성)가 다르게 나타났고, 이를
  최종 보고서에 함께 병기해 두 지표가 다른 질문에 답한다는
  것을 명시했다.

## 파이프라인 구조

① Data Understanding → ② Preprocessing → ③ Bottleneck Detection
→ ④ Root Cause Analysis (Human Review) → ⑤ Business Impact Simulation
→ ⑥ Scenario Recommendation (Human Approval) → ⑦ Report Builder
→ ⑧ PPT Generator

## 주요 설계 결정

- **규칙 기반 병목 판정**: "감"으로 판단했던 기준을
  `min_share_pct`, `min_delay_ratio` 임계값으로 표준화
- **Business Impact Simulation의 지연율 예측 제거**: "시간 단축 →
  지연율 감소"라는 검증 안 된 가정을 자동화하지 않기로 결정,
  Impact Score 계산까지만 수행
- **Join Engine**: BFS 기반 조인 경로 탐색으로, 기존 노트북에 있던
  숨겨진 이중 조인 버그를 발견하고 수정
- **MCP 서버 연동**: Claude Desktop과 대화형으로 파이프라인 실행,
  Human Review/Approval 지점에서 자연스럽게 대기

## 실행 방법

### 1. 개별 모듈 실행 (VS Code)
```powershell
cd agent/src
python main.py
```

### 2. 대화형 실행 (Claude Desktop + MCP)
`claude_desktop_config.json`에 `server.py`를 MCP 서버로 등록 후,
Claude Desktop에서 자연어로 파이프라인 진행 가능.

## 폴더 구조

```
agent/
├── config/     # Human Input (kpi_definition.yaml, approved_features.yaml 등)
├── src/        # 파이프라인 모듈 8개 + MCP 서버
└── outputs/    # 실행 결과물 (JSON, PNG, PPTX)
```

## 기술 스택

Python, pandas, scipy, matplotlib, graphviz, python-pptx,
Anthropic Claude API, MCP (Model Context Protocol)

## 한계 및 다음 단계

현재 파이프라인은 Olist 데이터셋 하나로만 검증되었다. 코드 구조는
데이터셋에 종속되지 않도록 설계했지만(`join_engine.py`의 BFS 기반
조인, threshold 기반 병목/원인 판정 등), 이는 설계 원칙이 일반화
가능하다는 것을 의미할 뿐, 실제로 다른 데이터셋에서 검증된 것은
아니다.

다음 단계로 다른 이커머스 데이터셋(예: Brazilian E-Commerce가
아닌 다른 공개 데이터셋)에 이 파이프라인을 적용해:
- `kpi_definition.yaml`, `preprocessing_policy.yaml` 등 설정
  파일만 교체해서 실제로 코드 수정 없이 재사용 가능한지 확인
- 병목이 3개 이상이거나, RCA에서 threshold를 통과하는 변수가
  없는 경우처럼 지금 다루지 않은 엣지 케이스를 발견하고 보완
- 이 검증 과정 자체를 프로젝트의 신뢰성을 보강하는 사례로 기록

하는 작업을 계획하고 있다.