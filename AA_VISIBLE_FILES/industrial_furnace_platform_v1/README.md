# 工业炉计算平台 V1

## 运行

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 初始化

```bash
curl -X POST http://127.0.0.1:8000/api/seed
```

## 验证

```bash
python3 -m compileall app tests
python3 -m pytest
```

## 已实现接口范围

1. 项目、名目、计算树、模板查询与创建。
2. 节点执行与结果快照保存。
3. 审批提交、通过、退回。
4. 草稿报告和正式报告生成。
5. 按 `step_type` 创建横向对比组并查询输出。
6. 基于 `X-Role` 请求头的最小权限控制。
7. 现场反馈、审图单、技术附件、图纸目录资料管理。
8. 同一设备的计算结果与多类型资料 AI 联合分析，输出物质流、能量流、信息流三流分析。
9. 按项目批量录入现场反馈、审图单、技术附件、图纸目录。

## AI API 配置

AI 联合分析通过 OpenAI 兼容接口调用外部大模型。未配置环境变量时，系统返回本地演示分析，便于开发测试。

```bash
export AI_API_URL="https://example.com/v1/chat/completions"
export AI_API_KEY="your-api-key"
export AI_MODEL="your-model-name"
```

## 权限示例

```bash
curl -H "X-Role: engineer" -X POST http://127.0.0.1:8000/api/seed
```
