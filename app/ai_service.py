from __future__ import annotations

import os


class AiProvider:
    def analyze(self, payload: dict) -> dict:
        raise NotImplementedError


def build_three_flow_assessment(payload: dict) -> dict:
    latest_results = payload.get("latest_results", [])
    success_count = sum(1 for result in latest_results if result.get("status") == "success")
    total_count = len(latest_results)
    has_results = total_count > 0

    material_flow = {
        "name": "物质流",
        "focus": "关注对象在流程网络中的输入、输出与传递是否连续有序",
        "status": "observed" if has_results else "insufficient_data",
        "evidence": [
            f"本次分析纳入 {total_count} 条节点结果",
            "可结合项目名目、树节点和节点输出继续检查物料路径完整性",
        ],
        "suggestion": "补充关键节点的输入输出定义，确保名目、节点和结果之间形成清晰传递链。",
    }
    energy_flow = {
        "name": "能量流",
        "focus": "关注驱动过程运行的时间、消耗、节奏与资源协同情况",
        "status": "stable" if success_count == total_count and has_results else "attention_needed",
        "evidence": [
            f"成功节点 {success_count}/{total_count}",
            "可继续结合 duration、执行频率和资源消耗指标扩展能量流评估",
        ],
        "suggestion": "增加执行耗时、资源占用和关键工艺节拍采集，形成能量流网络视图。",
    }
    information_flow = {
        "name": "信息流",
        "focus": "关注参数、规则、结果与诊断信息在系统中的传递与反馈闭环",
        "status": "stable" if has_results else "insufficient_data",
        "evidence": [
            f"分析类型为 {payload.get('analysis_type')}",
            "当前系统已具备参数、执行结果、审批与 AI 请求等基础信息链路",
        ],
        "suggestion": "将审批结论、对比结果和 AI 诊断回写到项目上下文，形成持续反馈回路。",
    }

    coordination_status = "协同连续" if has_results and success_count == total_count else "需要增强协同"
    return {
        "theory": "殷瑞钰院士三流理论",
        "three_flows": [material_flow, energy_flow, information_flow],
        "three_flow_state": {
            "name": "三流一态",
            "status": coordination_status,
            "conclusion": "当前分析以物质流、能量流、信息流三维联动为检查框架，重点判断流程是否动态有序、协同连续。",
        },
    }


class StubAiProvider(AiProvider):
    def analyze(self, payload: dict) -> dict:
        result_count = len(payload.get("latest_results", []))
        three_flow_assessment = build_three_flow_assessment(payload)
        return {
            "summary": f"基于殷瑞钰院士三流理论完成分析，当前共纳入 {result_count} 条结果。",
            "diagnosis_text": "本次诊断采用物质流、能量流、信息流三维框架，并给出三流一态协同结论。",
            "suggestions_json": [
                "按物质流检查关键名目与节点之间的输入输出衔接情况",
                "按能量流补充执行耗时、节拍与资源消耗指标",
                "按信息流把审批、对比和 AI 诊断接入统一反馈闭环",
            ],
            "risk_flags_json": ["stub_response"],
            "raw_response_json": {
                "provider": "stub",
                "project_id": payload.get("project_id"),
                "project_item_id": payload.get("project_item_id"),
                "analysis_type": payload.get("analysis_type"),
                "result_count": result_count,
                "analysis_framework": three_flow_assessment,
            },
        }


def get_ai_provider() -> AiProvider:
    provider = os.getenv("AI_PROVIDER", "stub").strip().lower()
    if provider == "stub":
        return StubAiProvider()
    return StubAiProvider()
