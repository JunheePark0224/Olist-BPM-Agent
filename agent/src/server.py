# server.py
"""
Olist Business Process Optimization Agent - MCP 서버
각 파이프라인 단계를 개별 tool로 등록해, Claude Desktop에서
"CSV 분석 시작해줘" 같은 대화로 단계별 실행이 가능하게 한다.

Human Review/Approval이 필요한 지점(④ Step1 후, ⑥ 후)은
결과를 반환하고 멈추며, 사람이 config 파일을 수정한 뒤
다음 tool을 호출하는 방식으로 자연스럽게 대화형 흐름이 만들어진다.
"""

from __future__ import annotations
from pathlib import Path
from mcp.server.mcpserver import MCPServer
from config import OUTPUT_DIR

import data_understanding
import preprocessing
import bottleneck_detection
import root_cause_analysis
import business_impact_simulation
import scenario_recommendation
import report_builder
import ppt_generator

mcp = MCPServer(name="Olist-BPM-Agent")


@mcp.tool(name="run_data_understanding", description="raw CSV들의 구조를 파악하고 스키마 설명을 생성합니다")
async def tool_data_understanding() -> dict:
    return await data_understanding.run()


@mcp.tool(name="run_preprocessing", description="KPI를 계산하고 데이터를 정제합니다")
async def tool_preprocessing() -> dict:
    return preprocessing.run()


@mcp.tool(name="run_bottleneck_detection", description="병목 구간을 규칙 기반으로 탐지합니다")
async def tool_bottleneck_detection() -> dict:
    return bottleneck_detection.run()


@mcp.tool(name="run_rca_step1", description="병목 구간별 후보 feature를 LLM이 제안합니다 (Human Review 필요)")
async def tool_rca_step1() -> dict:
    return await root_cause_analysis.run_step1()


@mcp.tool(name="run_rca_step2to4", description="승인된 feature로 effect size 계산, 해석, 다이어그램을 생성합니다 (approved_features.yaml 작성 후 호출)")
async def tool_rca_step2to4() -> dict:
    await root_cause_analysis.run_step2()
    await root_cause_analysis.run_step3()
    root_cause_analysis.run_step4()
    return {"status": "RCA 완료"}


@mcp.tool(name="run_business_impact", description="Impact Score를 계산합니다")
async def tool_business_impact() -> dict:
    return business_impact_simulation.run()


@mcp.tool(name="run_scenario_recommendation", description="개선 시나리오를 추천합니다 (Human Approval 필요)")
async def tool_scenario_recommendation() -> dict:
    return await scenario_recommendation.run()


@mcp.tool(name="run_report_generation", description="ab_test_design.yaml 작성 완료 후, 최종 Executive Report PPT를 생성합니다")
def tool_report_generation() -> dict:
    report_builder.run()
    path = ppt_generator.run(
        report_data_path=str(Path(OUTPUT_DIR) / "report_data.json"),
        output_path=str(Path(OUTPUT_DIR) / "executive_report.pptx"),
        images_dir=OUTPUT_DIR,
    )
    return {"status": "완료", "pptx_path": path}


@mcp.tool(name="run_pipeline_until_bottleneck", description="①~③ 단계를 한번에 실행합니다 (Data Understanding → Preprocessing → Bottleneck Detection)")
async def tool_pipeline_until_bottleneck() -> dict:
    await data_understanding.run()
    preprocessing.run()
    result = bottleneck_detection.run()
    return {"status": "①~③ 완료. run_rca_step1을 호출해 후보 feature를 확인하세요.", "bottleneck_report": result}


if __name__ == "__main__":
    mcp.run()