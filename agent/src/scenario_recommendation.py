# scenario_recommendation.py
"""
⑥ Improvement Scenario Recommendation 모듈
- simulation_report.json의 시나리오 후보들(변수×그룹 단위)을 LLM이 검토해
  "같은 변수 안에서만" 대표 시나리오를 하나씩 생성
- recommended_scenario.json(Agent 내부 데이터, Source of Truth)과
  recommended_scenario.md(사람이 읽는 보고서, JSON을 렌더링한 결과)를 생성

설계 원칙: Effect Size(η²/r²)와 Impact Score는 역할이 다르다.
- Effect Size: "왜 이 원인을 봐야 하는가" (④ RCA에서 이미 검증된 원인의
  통계적 중요도)
- Impact Score: "이걸 개선하면 얼마나 이득인가" (⑤에서 계산된 비즈니스
  영향력)

여러 그룹(예: 2월+3월)을 하나로 합치면 Impact Score가 커지는데, 이는
"묶는 방법" 때문에 커진 것이지 원인 자체가 더 중요해진 게 아니다. 따라서
최종 시나리오의 우선순위(priority)는 LLM이 임의로 정하지 않고, RCA가
이미 결정한 effect_size_pct 순서를 그대로 따른다. LLM은 변수 안에서만
그룹을 묶어 대표 시나리오를 만들고, Impact Score는 그 시나리오의
"기대 효과 크기"를 보여주는 근거 정보로 함께 제시한다.

이렇게 하면 변수 개수만큼 시나리오가 나오고(합산으로 인한 순위 역전이
없고), 사람은 "Effect Size가 큰 원인 순"으로 검토하면서 각 시나리오의
"Impact Score(실제 기대 효과)"를 함께 참고해 최종 승인 여부를 판단할 수
있다.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List
from config import OUTPUT_DIR, CHAT_MODEL, ensure_dir, get_anthropic_client, log
from root_cause_analysis import load_json


# =========================
# 1. LLM 시나리오 추천 (변수별 대표 시나리오 1개씩)
# =========================
SCENARIO_SYSTEM_PROMPT = """당신은 이커머스 물류 운영 컨설턴트입니다.
주어진 Business Impact Simulation 후보 목록을 보고, variable(변수)별로
대표 개선 시나리오를 정확히 하나씩 만드세요.

⚠️ 매우 중요:
- 시나리오는 반드시 "같은 variable 안에서만" 그룹을 묶으세요. 예를 들어
  carrier_month=2와 carrier_month=3처럼 같은 변수의 값들은 비즈니스적으로
  타당하면(예: 카니발 시즌) 하나로 묶을 수 있습니다. 하지만 서로 다른
  variable(예: carrier_month와 seller_dayofweek)은 절대 하나의 시나리오로
  묶지 마세요.
- variable마다 정확히 1개의 대표 시나리오만 만드세요. 입력에 등장하는
  variable의 개수만큼 시나리오가 나와야 합니다.
- 같은 variable 내에서 여러 값을 묶을지 말지는, 그 값들이 실제로 같은
  비즈니스 사건을 나타내는지로 판단하세요 (예: 2월+3월=카니발 시즌).
  억지로 묶지 말고, 묶을 이유가 없으면 impact_score가 가장 큰 그룹
  하나만 대표로 쓰세요.
- 시나리오에 포함되는 값은 반드시 입력 후보 목록에 실제로 존재하는
  것만 사용하세요. 목록에 없는 값을 지어내지 마세요.

각 시나리오마다 다음을 작성하세요:
- variable: 원본 변수명 (입력에 있는 그대로)
- title: 영어로, 간결한 개선안 이름
- included_values: 이 시나리오에 포함된 원본 후보의 label 목록
  (입력에 있던 label을 그대로 사용)
- impact_score: 포함된 후보들의 impact_score 합계
  (하나만 포함되면 그 값 그대로)
- reason: 왜 이 값들을 함께(또는 단독으로) 다뤘는지 2문장 이내, 영어
- expected_effect: 개선했을 때 기대 효과 1문장, 영어

반드시 아래 JSON 하나만, 다른 설명 없이 출력하세요.

{
  "recommended_scenarios": [
    {
      "variable": "customer_state",
      "title": "RJ Delivery Optimization",
      "included_values": ["customer_state=RJ"],
      "impact_score": 788027,
      "reason": "...",
      "expected_effect": "..."
    }
  ]
}
"""

async def recommend_scenarios(scenarios: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    LLM에게 simulation_report.json의 시나리오 후보 전체를 전달해
    변수별 대표 시나리오 추천을 받는다. 최종 순위는 LLM이 정하지 않고,
    이 함수가 RCA의 effect_size_pct 기준으로 직접 정렬한다 (설계 원칙:
    RCA가 정한 원인의 중요도를 이후 단계가 덮어쓰지 않는다).
    API 호출 실패 시에도 파이프라인이 죽지 않도록 예외를 처리한다.

    Args:
        scenarios: simulation_report.json의 scenarios 리스트
            (각 원소에 variable, effect_size_pct가 포함되어 있어야 함)

    Returns:
        Dict[str, Any]: {"recommended_scenarios": [...]}.
        각 원소에 effect_size_pct, priority, id가 채워지며,
        priority는 effect_size_pct 내림차순으로 부여됨.
    """
    user_content = json.dumps({"candidates": scenarios}, ensure_ascii=False)

    variables_in_input = {s["variable"] for s in scenarios}
    fallback = {
        "recommended_scenarios": [
            {
                "variable": var,
                "title": var,
                "included_values": [s["label"] for s in scenarios if s["variable"] == var][:1],
                "impact_score": max(s["impact_score"] for s in scenarios if s["variable"] == var),
                "reason": "LLM 호출 실패로 자동 생성하지 못했습니다.",
                "expected_effect": "N/A",
            }
            for var in variables_in_input
        ]
    }

    try:
        client = get_anthropic_client()
        response = await client.messages.create(
            model=CHAT_MODEL,
            max_tokens=2500,
            system=SCENARIO_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        text_blocks = [block.text for block in response.content if block.type == "text"]
        if not text_blocks:
            raise RuntimeError("응답에 텍스트 블록이 없습니다.")
        content = text_blocks[0].strip()

        decoder = json.JSONDecoder()
        first_brace = content.index("{")
        result, _ = decoder.raw_decode(content, first_brace)

        # 최종 순위는 RCA의 effect_size_pct 기준으로 재정렬한다.
        effect_size_by_var = {}
        for s in scenarios:
            if s["variable"] not in effect_size_by_var:
                effect_size_by_var[s["variable"]] = s.get("effect_size_pct", 0)

        for rec in result["recommended_scenarios"]:
            rec["effect_size_pct"] = effect_size_by_var.get(rec["variable"], 0)

        result["recommended_scenarios"].sort(key=lambda r: r["effect_size_pct"], reverse=True)
        for i, rec in enumerate(result["recommended_scenarios"]):
            rec["priority"] = i + 1
            rec["id"] = f"S{i+1}"

        log(f"시나리오 추천 완료: {len(result['recommended_scenarios'])}개 (effect_size_pct 순 정렬)")
        return result
    except Exception as e:
        log(f"시나리오 추천 실패: {e}")
        return fallback


# =========================
# 2. Markdown 렌더링 (JSON을 사람이 읽는 문서로 변환)
# =========================
def render_scenario_markdown(recommended: Dict[str, Any]) -> str:
    """
    recommended_scenario.json 내용을 사람이 읽기 좋은 Markdown으로 렌더링.
    JSON이 원본(Source of Truth)이고, 이 함수는 단순히 보여주기 위한
    변환만 수행한다. Effect Size(원인 중요도)와 Impact Score(기대 효과)를
    둘 다 표시해, 사람이 두 지표를 함께 보고 판단할 수 있게 한다.

    Args:
        recommended: recommend_scenarios()의 반환값

    Returns:
        str: Markdown 문서 내용
    """
    lines = ["# Recommended Improvement Scenarios", ""]
    for s in recommended["recommended_scenarios"]:
        lines.append(f"## {s['id']}. {s['title']}")
        lines.append("")
        lines.append(f"**Variable:** {s['variable']}")
        lines.append(f"**Included Values:** {', '.join(s['included_values'])}")
        lines.append(f"**Effect Size:** {s['effect_size_pct']}%")
        lines.append(f"**Impact Score:** {s['impact_score']:,.0f}")
        lines.append("")
        lines.append(f"**Reason:** {s['reason']}")
        lines.append("")
        lines.append(f"**Expected Effect:** {s['expected_effect']}")
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


# =========================
# 3. 전체 실행 함수
# =========================
async def run(output_dir: str = OUTPUT_DIR) -> Dict[str, str]:
    """
    ⑥ Improvement Scenario Recommendation 전체 실행:
    simulation_report.json → LLM 추천(변수별 대표 시나리오) →
    effect_size_pct 기준 재정렬 → recommended_scenario.json +
    recommended_scenario.md 생성

    Args:
        output_dir: simulation_report.json이 있고 결과물을 저장할 폴더

    Returns:
        Dict[str, str]: 생성된 파일 경로들
    """
    output_dir = ensure_dir(output_dir)

    simulation_report = load_json(str(Path(output_dir) / "simulation_report.json"))
    scenarios = simulation_report["scenarios"]

    recommended = await recommend_scenarios(scenarios)

    json_path = Path(output_dir) / "recommended_scenario.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(recommended, f, ensure_ascii=False, indent=2)
    log(f"recommended_scenario.json 저장 완료: {json_path}")

    md_content = render_scenario_markdown(recommended)
    md_path = Path(output_dir) / "recommended_scenario.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    log(f"recommended_scenario.md 저장 완료: {md_path}")

    return {"recommended_scenario_json": str(json_path), "recommended_scenario_md": str(md_path)}