import json
import os
import urllib.error
import urllib.request
from typing import Any


def _artifact_answer(prompt: str) -> str:
    try:
        data = json.loads(prompt)
    except json.JSONDecodeError:
        return "没有读取到可用于回答的项目资料。"
    question = str(data.get("question") or "").strip()
    retrieved_chunks = data.get("retrieved_chunks") or []
    if retrieved_chunks:
        answer_lines = [f"根据已检索到的跨文件资料片段，针对“{question or '当前问题'}”可以看到："]
        for index, chunk in enumerate(retrieved_chunks[:8], start=1):
            snippet = " ".join(str(chunk.get("content") or "").split())[:220]
            answer_lines.append(f"{index}. {chunk.get('type_name') or '项目资料'}《{chunk.get('title') or '未命名资料'}》片段 {chunk.get('chunk_index', 0)}：{snippet or '未读取到片段内容'}")
        return "\n".join(answer_lines)
    artifacts = data.get("artifacts") or []
    if not artifacts:
        return "项目资料中还没有可用于回答这个问题的内容。请先在项目资料里上传相关文字或文件说明。"
    matched = []
    keywords = [word for word in question.replace("，", " ").replace("。", " ").replace("？", " ").replace("?", " ").split() if len(word) >= 2]
    for artifact in artifacts:
        title = str(artifact.get("title") or "")
        content = str(artifact.get("content") or artifact.get("content_preview") or "")
        text = f"{title}\n{content}"
        if not keywords or any(keyword in text for keyword in keywords):
            matched.append((artifact.get("type_name") or artifact.get("type") or "项目资料", title, content))
    rows = matched or [(artifact.get("type_name") or artifact.get("type") or "项目资料", artifact.get("title") or "未命名资料", artifact.get("content") or artifact.get("content_preview") or "") for artifact in artifacts]
    answer_lines = [f"根据项目资料，针对“{question or '当前问题'}”可以看到："]
    for index, (type_name, title, content) in enumerate(rows[:6], start=1):
        snippet = " ".join(str(content).split())[:180]
        if "当前版本只能直接读取文本类附件正文" in snippet or "PDF、Word、Excel" in snippet:
            snippet = "这条资料是旧版上传记录，只保存了附件清单，没有解析到 Word 正文；请重新上传 .docx，系统会自动解析正文。"
        answer_lines.append(f"{index}. {type_name}《{title}》记录：{snippet or '未填写具体内容'}")
    if len(rows) > 6:
        answer_lines.append(f"另外还有 {len(rows) - 6} 条项目资料可继续复核。")
    return "\n".join(answer_lines)


def run_joint_analysis(prompt: str) -> dict[str, Any]:
    api_url = os.getenv("AI_API_URL")
    api_key = os.getenv("AI_API_KEY")
    model = os.getenv("AI_MODEL", "industrial-furnace-v1")
    if not api_url or not api_key:
        answer = _artifact_answer(prompt)
        return {
            "provider": "mock",
            "answer": answer,
            "summary": answer,
        }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是工业炉项目资料问答助手。只根据用户提供的项目资料、检索片段和计算记录回答问题，回答应直接、简洁、像聊天一样。优先使用 retrieved_chunks，这些是系统从当前项目多个文件切片和向量检索得到的相关片段。当前系统已支持解析 .docx Word 正文；资料内容中出现“已解析 Word 正文”时，必须直接基于其后面的正文回答。资料内容中出现“当前版本只能直接读取文本类附件正文”或“PDF、Word、Excel”时，说明这是旧版上传记录，应提示用户重新上传 .docx，而不要说当前系统不能读取 Word。"},
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
    return {"provider": "api", "answer": content, "summary": content, "raw": data}
