# 13 错误码与文件存储规格

## 1. 错误结构

```json
{
  "code": "PARAM_INVALID",
  "message": "参数不合法",
  "details": {},
  "request_id": "req-xxx"
}
```

## 2. 错误码

| code | HTTP | 说明 |
|---|---|---|
| `PARAM_INVALID` | 400 | 参数不合法 |
| `TEMPLATE_NOT_FOUND` | 404 | 模板不存在 |
| `EXECUTION_FAILED` | 500 | 执行失败 |
| `REPORT_FAILED` | 500 | 报告生成失败 |
| `PERMISSION_DENIED` | 403 | 权限不足 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `STATE_INVALID` | 409 | 状态不允许 |
| `FILE_INVALID` | 400 | 文件不合法 |
| `AI_PROVIDER_UNAVAILABLE` | 503 | AI 服务不可用 |
| `ARTIFACT_TYPE_INVALID` | 400 | 资料类型不支持 |

## 3. 存储路径

| 类型 | 路径 |
|---|---|
| 输入文件 | `storage/projects/{project_code}/inputs/{execution_id}/` |
| 输出文件 | `storage/projects/{project_code}/outputs/{execution_id}/` |
| 报告文件 | `storage/projects/{project_code}/reports/{report_id}/` |
| 日志文件 | `storage/projects/{project_code}/logs/{execution_id}/` |
| 归档文件 | `storage/projects/{project_code}/archive/{report_id}/` |
| 项目资料 | `storage/projects/{project_code}/artifacts/{artifact_type}/` |
| AI 分析记录 | `storage/projects/{project_code}/ai-analyses/{analysis_id}/` |

## 4. 文件元数据

1. `file_id`
2. `file_type`
3. `original_name`
4. `storage_path`
5. `content_type`
6. `size_bytes`
7. `checksum`
8. `created_by`
9. `created_at`

## 5. 约束

1. 文件路径不得由用户直接传入。
2. 文件名必须服务端生成。
3. 报告归档后不得覆盖原文件。
4. 下载必须校验权限。
5. 项目资料允许 V1.0 先以文本内容入库，后续文件化时使用项目资料路径。
6. AI 分析必须保存请求上下文和响应内容，真实 API Key 不得入库。
