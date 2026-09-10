# labels.py
"""
파생 변수 값의 표시용 라벨.

approved_features.yaml의 derived 정의(extract: month / dayofweek)로 만들어진
컬럼은 값이 0~11, 0~6 같은 정수다. 이 값이 LLM 프롬프트나 덱에 그대로 가면
해석이 어긋난다 — 실제로 Step 3 LLM이 dayofweek=0을 "일요일", 5를 "금요일"로
잘못 읽었다 (pandas는 0=월요일, 5=토요일).

④ RCA(LLM 입력)와 ⑧ Report Builder(덱 표시)가 같은 매핑을 쓰도록 여기 한 곳에 둔다.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

WEEKDAY_NAMES_KO = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


def format_derived_value(value: Any, extract: str) -> str:
    """
    파생 컬럼의 원시값을 사람이 읽는 라벨로 바꾼다.

    Args:
        value: 원시값 (예: 5, 5.0, "5.0")
        extract: approved_features.yaml derived의 extract 유형 (month / dayofweek / hour)

    Returns:
        str: "5월", "토요일", "14시" 등. 알 수 없는 extract면 값 그대로.
    """
    number = int(float(value))
    if extract == "month":
        return f"{number}월"
    if extract == "dayofweek":
        return WEEKDAY_NAMES_KO[number]
    if extract == "hour":
        return f"{number}시"
    return str(value)


def build_value_formatters(approved_features_all: Dict[str, Any]) -> Dict[str, Callable[[Any], str]]:
    """
    approved_features.yaml 전체에서 {파생 변수명: 라벨 함수}를 만든다.
    파생이 아닌 변수는 포함되지 않는다 (호출측에서 값을 그대로 쓴다).

    Args:
        approved_features_all: approved_features.yaml 전체

    Returns:
        Dict[str, Callable]: 변수명 → 라벨 함수
    """
    formatters: Dict[str, Callable[[Any], str]] = {}
    for stage_conf in approved_features_all.values():
        if not isinstance(stage_conf, dict):
            continue
        for var, spec in stage_conf.get("derived", {}).items():
            extract = spec.get("extract")
            if extract:
                formatters[var] = lambda v, e=extract: format_derived_value(v, e)
    return formatters
