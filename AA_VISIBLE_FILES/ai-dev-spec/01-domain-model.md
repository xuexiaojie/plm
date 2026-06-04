# 01 领域模型规格

## 1. 核心对象

| 对象 | 中文名 | 业务含义 |
|---|---|---|
| `Project` | 项目 | 承载一次工程、设计或运行复核任务 |
| `ProjectItem` | 名目 | 项目内一个炉型实例或独立计算对象 |
| `CalcNode` | 计算节点 | 名目计算树中的目录或计算节点 |
| `CalcStepTemplate` | 计算模板 | 可复用算法、输入输出、报告规则定义 |
| `CalcExecution` | 执行记录 | 一次计算任务及快照 |
| `CalcResult` | 计算结果 | 标准化输出、警告、错误、约束判定 |
| `ApprovalRequest` | 审批申请 | 对执行结果或报告的审批流程 |
| `ApprovalLog` | 审批日志 | 审批动作记录 |
| `GeneratedReport` | 生成报告 | 草稿、待审、正式、归档报告元数据 |
| `ComparisonGroup` | 对比组 | 同类计算结果的横向对比配置 |
| `ProjectArtifact` | 项目资料 | 现场反馈、审图单、技术附件、图纸目录等工程资料 |
| `AiAnalysis` | AI 分析 | 同一设备的计算结果与项目资料联合分析记录 |

## 2. 名目定义

名目是项目内的业务计算单元。一个名目对应一个明确的炉型实例或计算对象，并承载一棵计算树。

示例：
1. `1 号步进炉设计校核`
2. `2 号辊底炉热处理复核`
3. `环形炉炉温制度优化`

## 3. 对象关系

1. `Project` 1:N `ProjectItem`
2. `ProjectItem` 1:N `CalcNode`
3. `CalcNode` N:1 `CalcStepTemplate`，仅计算节点允许绑定模板。
4. `CalcNode` 1:N `CalcExecution`
5. `CalcExecution` 1:1 `CalcResult`
6. `CalcExecution` 1:N `GeneratedReport`
7. `CalcExecution` 1:N `ApprovalRequest`
8. `ApprovalRequest` 1:N `ApprovalLog`
9. `ComparisonGroup` N:N `CalcResult`
10. `Project` 1:N `ProjectArtifact`
11. `ProjectItem` 1:N `ProjectArtifact`，资料也可只挂项目。
12. `Project` 1:N `AiAnalysis`

## 4. 生命周期

### 4.1 项目

`DRAFT -> ACTIVE -> CLOSED -> ARCHIVED`

### 4.2 名目

`DRAFT -> ACTIVE -> DISABLED`

### 4.3 执行

`PENDING -> RUNNING -> SUCCESS | FAILED | CANCELLED`

### 4.4 审批

`DRAFT -> SUBMITTED -> APPROVED | RETURNED -> SUBMITTED -> APPROVED -> ARCHIVED`

## 5. 页面导航

页面必须按以下业务路径组织：

`项目列表 -> 项目详情 -> 名目列表 -> 计算树 -> 节点计算 -> 执行结果 -> 审批 -> 报告 -> 对比 -> 资料管理 -> AI 联合分析`

## 6. 项目资料类型

| code | 中文名 | 说明 |
|---|---|---|
| `site_feedback` | 现场反馈 | 来自现场安装、调试、运行或问题反馈的文本资料 |
| `drawing_review` | 审图单 | 设计审查、图纸会审、审图意见类资料 |
| `technical_attachment` | 技术附件 | 设备参数、技术协议、计算附件、说明附件 |
| `drawing_catalog` | 图纸目录 | 图纸清单、版本目录、专业图纸索引 |

项目资料支持批量录入。批量录入以项目为入口，每条资料可选择绑定 `project_item_id`，也可保持为空作为项目级资料。

## 7. AI 联合分析对象

AI 联合分析以设备名称为主线，例如“装出钢机”。分析上下文由以下内容组成：

1. 同一项目下的一个或多个 `CalcExecution` 和 `CalcResult`。
2. 同一项目下的现场反馈、审图单、技术附件、图纸目录。
3. 用户输入的问题和分析目标。

系统通过大模型 API 发起分析，并保存 `AiAnalysis` 记录。未配置大模型 API 时返回演示分析结果。

## 8. 示例 JSON

```json
{
  "project": {
    "code": "PRJ-2026-001",
    "name": "1780 热轧产线工业炉样例项目"
  },
  "item": {
    "code": "ITEM-WBF-001",
    "name": "1 号步进炉设计校核",
    "furnace_type": "walking_beam_furnace"
  },
  "node": {
    "name": "升温计算",
    "node_type": "calc",
    "template_code": "walking_beam_furnace_temp_profile_v1"
  }
}
```
