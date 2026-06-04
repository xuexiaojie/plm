# 02 数据库 Schema 规格

## 1. 通用字段

所有业务表必须包含：

1. `id INTEGER PRIMARY KEY`
2. `created_at DATETIME NOT NULL`
3. `updated_at DATETIME NOT NULL`
4. `deleted_at DATETIME NULL`

## 2. 表结构

### 2.1 projects

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | integer | PK |
| `code` | string | unique, not null |
| `name` | string | not null |
| `owner_user_id` | integer | not null |
| `status` | string | not null, default `DRAFT` |
| `description` | text | nullable |

### 2.2 project_items

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | integer | PK |
| `project_id` | integer | FK projects.id, not null |
| `code` | string | not null |
| `name` | string | not null |
| `furnace_type` | string | not null |
| `business_scope` | string | nullable |
| `design_stage` | string | nullable |
| `status` | string | not null, default `DRAFT` |
| `description` | text | nullable |

唯一约束：`project_id + code`

### 2.3 calc_nodes

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | integer | PK |
| `project_item_id` | integer | FK project_items.id, not null |
| `parent_id` | integer | FK calc_nodes.id, nullable |
| `name` | string | not null |
| `node_type` | string | `folder` 或 `calc` |
| `sort_order` | integer | not null, default 0 |
| `template_id` | integer | FK calc_step_templates.id, nullable |
| `status` | string | not null, default `ACTIVE` |

索引：`project_item_id`、`parent_id`、`template_id`

### 2.4 calc_step_templates

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | integer | PK |
| `code` | string | unique, not null |
| `name` | string | not null |
| `category` | string | not null |
| `step_type` | string | not null |
| `furnace_type` | string | not null |
| `version` | string | not null |
| `executor_type` | string | not null |
| `entrypoint` | string | not null |
| `input_fields_json` | json/text | not null |
| `output_fields_json` | json/text | not null |
| `formula_source` | text | nullable |
| `applicable_scope` | text | nullable |
| `status` | string | not null, default `ACTIVE` |

### 2.5 calc_executions

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | integer | PK |
| `execution_no` | string | unique, not null |
| `project_id` | integer | FK projects.id, not null |
| `project_item_id` | integer | FK project_items.id, not null |
| `node_id` | integer | FK calc_nodes.id, not null |
| `template_id` | integer | FK calc_step_templates.id, not null |
| `status` | string | not null |
| `input_snapshot_json` | json/text | not null |
| `template_snapshot_json` | json/text | not null |
| `executor_version` | string | not null |
| `started_at` | datetime | nullable |
| `finished_at` | datetime | nullable |
| `duration_ms` | integer | nullable |

### 2.6 calc_results

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | integer | PK |
| `execution_id` | integer | FK calc_executions.id, unique, not null |
| `success` | boolean | not null |
| `feasible` | boolean | not null |
| `output_json` | json/text | not null |
| `warnings_json` | json/text | not null |
| `errors_json` | json/text | not null |
| `logs_json` | json/text | not null |

### 2.7 approval_requests

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | integer | PK |
| `execution_id` | integer | FK calc_executions.id, not null |
| `status` | string | not null |
| `submitted_by` | integer | not null |
| `submitted_at` | datetime | nullable |
| `current_approver_id` | integer | nullable |

### 2.8 approval_logs

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | integer | PK |
| `approval_request_id` | integer | FK approval_requests.id, not null |
| `action` | string | not null |
| `from_status` | string | nullable |
| `to_status` | string | not null |
| `comment` | text | nullable |
| `actor_user_id` | integer | not null |

### 2.9 generated_reports

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | integer | PK |
| `report_no` | string | unique, nullable |
| `execution_id` | integer | FK calc_executions.id, not null |
| `status` | string | not null |
| `version` | string | not null |
| `file_path` | string | nullable |
| `watermark` | string | nullable |

### 2.10 comparison_groups

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | integer | PK |
| `name` | string | not null |
| `step_type` | string | not null |
| `created_by` | integer | not null |

### 2.11 comparison_items

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | integer | PK |
| `comparison_group_id` | integer | FK comparison_groups.id, not null |
| `result_id` | integer | FK calc_results.id, not null |

### 2.12 project_artifacts

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | integer | PK |
| `project_id` | integer | FK projects.id, not null |
| `project_item_id` | integer | FK project_items.id, nullable |
| `artifact_type` | string | not null，枚举：`site_feedback`、`drawing_review`、`technical_attachment`、`drawing_catalog` |
| `title` | string | not null |
| `source_code` | string | nullable |
| `content` | text | not null |
| `status` | string | not null, default `ACTIVE` |

索引：`project_id`、`project_item_id`、`artifact_type`

### 2.13 ai_analyses

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | integer | PK |
| `project_id` | integer | FK projects.id, not null |
| `project_item_id` | integer | FK project_items.id, nullable |
| `equipment_name` | string | not null |
| `analysis_type` | string | not null |
| `request_json` | json/text | not null |
| `response_json` | json/text | not null |
| `provider` | string | not null |
| `status` | string | not null |

## 3. 实现要求

1. 所有 JSON 字段在 SQLite 中可用 Text 存储，在 PostgreSQL 中可迁移为 JSONB。
2. 所有状态字段必须使用统一枚举。
3. 所有删除使用 `deleted_at` 逻辑删除。
4. 项目资料批量录入必须在同一事务内提交。
5. AI 分析必须保存完整请求上下文和响应结果，便于追溯。
