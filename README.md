# Olist Business Process Optimization Agent

Olist 이커머스 배송 데이터를 기반으로, 병목 탐지 → 원인 분석 → 
개선 시나리오 추천 → A/B Test 설계 → Executive Report 생성까지 
전체 분석 프로세스를 자동화하는 AI Agent 파이프라인.

## 배경

기존에 노트북(Jupyter)으로 수동 진행했던 8단계 데이터 분석 프로세스를 
Agent 파이프라인으로 재구현하며, LLM과 Python의 역할을 명확히 분리했다.
- LLM: 후보 제안, 해석, 카테고리 그룹핑처럼 판단이 필요한 영역
- Python: 통계 계산(η²/r²), 규칙 기반 필터링처럼 재현 가능해야 하는 영역

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
\`\`\`powershell
cd agent/src
python main.py
\`\`\`

### 2. 대화형 실행 (Claude Desktop + MCP)
\`claude_desktop_config.json\`에 \`server.py\`를 MCP 서버로 등록 후, 
Claude Desktop에서 자연어로 파이프라인 진행 가능.

## 폴더 구조

\`\`\`
agent/
├── config/     # Human Input (kpi_definition.yaml, approved_features.yaml 등)
├── src/        # 파이프라인 모듈 8개 + MCP 서버
└── outputs/    # 실행 결과물 (JSON, PNG, PPTX)
\`\`\`

## 기술 스택

Python, pandas, scipy, matplotlib, graphviz, python-pptx, 
Anthropic Claude API, MCP (Model Context Protocol)