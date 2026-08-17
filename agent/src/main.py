# main.py
"""
전체 파이프라인을 순서대로 실행하는 오케스트레이터.
Human Review/Approval이 필요한 지점에서는 멈추고 안내 메시지를 출력한다.
"""

import asyncio
import data_understanding
import preprocessing
import bottleneck_detection
import root_cause_analysis
import business_impact_simulation
import scenario_recommendation
import report_builder
import ppt_generator


async def main():
    print("=== ① Data Understanding ===")
    await data_understanding.run()

    print("=== ② Preprocessing ===")
    preprocessing.run()

    print("=== ③ Bottleneck Detection ===")
    bottleneck_detection.run()

    print("=== ④ RCA Step 1: 후보 feature 제안 ===")
    await root_cause_analysis.run_step1()
    print("\n⚠️  Human Review 필요: candidate_features_*.md를 확인하고")
    print("    agent/config/approved_features.yaml을 작성한 뒤 Enter를 눌러주세요.")
    input()

    print("=== ④ RCA Step 2~4 ===")
    await root_cause_analysis.run_step2()
    await root_cause_analysis.run_step3()
    root_cause_analysis.run_step4()

    print("=== ⑤ Business Impact Simulation ===")
    business_impact_simulation.run()

    print("=== ⑥ Scenario Recommendation ===")
    await scenario_recommendation.run()
    print("\n⚠️  Human Approval 필요: recommended_scenario.md를 확인하고")
    print("    agent/config/ab_test_design.yaml을 작성한 뒤 Enter를 눌러주세요.")
    input()

    print("=== ⑦ Report Builder ===")
    report_builder.run()

    print("=== ⑧ PPT Generator ===")
    ppt_generator.run(
        report_data_path="../outputs/report_data.json",
        output_path="../outputs/executive_report.pptx",
        images_dir="../outputs",
    )

    print("\n✅ 파이프라인 완료! executive_report.pptx를 확인하세요.")


if __name__ == "__main__":
    asyncio.run(main())