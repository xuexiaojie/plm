import json
import os
import urllib.error
import urllib.request
from typing import Any


def run_joint_analysis(prompt: str) -> dict[str, Any]:
    api_url = os.getenv("AI_API_URL")
    api_key = os.getenv("AI_API_KEY")
    model = os.getenv("AI_MODEL", "industrial-furnace-v1")
    if not api_url or not api_key:
        return {
            "provider": "mock",
            "summary": "已完成演示联合分析。当前未配置 AI_API_URL 或 AI_API_KEY，因此返回本地模拟结论，并按物质流、能量流、信息流三个维度组织。",
            "three_flows": {
                "material_flow": ["核对装出钢机输送节拍、坯料规格、出入炉路径与计算对象是否一致"],
                "energy_flow": ["核对温度制度、热量供给、保温时间和表里温差约束对能量利用的影响"],
                "information_flow": ["核对现场反馈、审图单、技术附件、图纸目录版本与计算输入之间的信息一致性"],
            },
            "risks": ["需核对现场反馈与计算假设是否一致", "需确认审图单意见是否已闭环", "需校验技术附件中的设备参数版本"],
            "conflicts": ["若图纸目录版本晚于计算输入，应重新复核计算边界条件"],
            "recommendations": ["将同一设备的计算、现场反馈、审图单、技术附件、图纸目录纳入同一分析包", "正式环境配置 AI_API_URL、AI_API_KEY、AI_MODEL 后调用大模型 API"],
        }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是工业炉工程计算审查助手，按物质流、能量流、信息流三个维度输出结构化、可追溯、面向工程闭环的分析。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"provider": "api", "summary": "大模型 API 调用失败", "errors": [str(exc)]}

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return {"provider": "api", "summary": content, "raw": data}
