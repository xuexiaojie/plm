# 06 API 契约规格

## 1. 通用响应

```json
{
  "data": {},
  "error": null,
  "request_id": "req-xxx"
}
```

## 2. 通用错误

```json
{
  "data": null,
  "error": {
    "code": "PARAM_INVALID",
    "message": "参数不合法",
    "details": {}
  },
  "request_id": "req-xxx"
}
```

## 3. 项目 API

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/projects` | read | 项目列表 |
| POST | `/api/projects` | project:create | 创建项目 |
| GET | `/api/projects/{project_id}` | read | 项目详情 |
| PATCH | `/api/projects/{project_id}` | project:update | 更新项目 |

## 4. 名目 API

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/projects/{project_id}/items` | read | 名目列表 |
| POST | `/api/projects/{project_id}/items` | item:create | 创建名目 |
| GET | `/api/items/{item_id}` | read | 名目详情 |

## 5. 计算树 API

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/items/{item_id}/nodes` | read | 节点树 |
| POST | `/api/items/{item_id}/nodes` | node:create | 新增节点 |
| PATCH | `/api/nodes/{node_id}` | node:update | 更新节点 |

## 6. 模板 API

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/templates` | read | 模板列表 |
| POST | `/api/templates` | template:manage | 创建模板 |
| GET | `/api/templates/{template_id}` | read | 模板详情 |

## 7. 执行 API

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/nodes/{node_id}/executions` | execution:run | 执行节点 |
| GET | `/api/executions/{execution_id}` | read | 执行详情 |
| GET | `/api/executions/{execution_id}/result` | read | 执行结果 |

## 8. 审批 API

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/executions/{execution_id}/approval` | approval:submit | 提交审批 |
| POST | `/api/approvals/{approval_id}/approve` | approval:review | 审批通过 |
| POST | `/api/approvals/{approval_id}/return` | approval:review | 退回 |

## 9. 报告 API

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/executions/{execution_id}/reports` | report:create | 生成报告 |
| GET | `/api/reports/{report_id}` | read | 报告详情 |
| GET | `/api/reports/{report_id}/download` | report:download | 下载报告 |

## 10. 对比与 AI API

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/comparisons` | comparison:create | 创建对比组 |
| GET | `/api/comparisons/{group_id}` | read | 对比结果 |
| POST | `/api/projects/{project_id}/ai-analyses` | ai:analyze | 发起项目 AI 联合分析 |
| GET | `/api/projects/{project_id}/ai-analyses` | read | AI 分析记录列表 |

## 11. 项目资料 API

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/artifact-types` | read | 资料类型字典 |
| POST | `/api/projects/{project_id}/artifacts` | artifact:manage | 单条录入项目资料 |
| POST | `/api/projects/{project_id}/artifacts/batch` | artifact:manage | 按项目批量录入资料 |
| GET | `/api/projects/{project_id}/artifacts` | read | 查询项目资料，可按 `project_item_id` 过滤 |

批量录入请求示例：

```json
{
  "items": [
    {
      "artifact_type": "site_feedback",
      "title": "现场反馈",
      "source_code": "FB-001",
      "content": "现场反馈内容"
    },
    {
      "artifact_type": "drawing_review",
      "title": "审图单",
      "source_code": "DR-001",
      "content": "审图单内容"
    }
  ]
}
```

AI 联合分析请求示例：

```json
{
  "project_item_id": 1,
  "equipment_name": "装出钢机",
  "execution_ids": [1],
  "artifact_ids": [1, 2, 3, 4],
  "question": "请联合分析装出钢机计算、现场反馈、审图单、技术附件和图纸目录，并按物质流、能量流、信息流输出结论。"
}
```

## 12. 约束

1. 每个 API 必须有 Pydantic 请求和响应 Schema。
2. 每个 API 必须有错误码测试。
3. 权限字段必须与 `12-permission-matrix.md` 一致。
