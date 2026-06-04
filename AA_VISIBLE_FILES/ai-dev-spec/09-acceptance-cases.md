# 09 验收用例规格

## 1. 用例 AC-001 创建项目和名目

Given 用户以普通计算人员登录，并打开项目页。

When 用户创建项目 `PRJ-2026-001`，并创建名目 `ITEM-WBF-001`。

Then 系统返回创建成功，名目详情中显示炉型 `walking_beam_furnace`。

## 2. 用例 AC-002 创建计算树

Given 已存在样例名目。

When 用户新增根节点和一个计算节点，并绑定模板 `walking_beam_furnace_temp_profile_v1`。

Then 结构树页显示节点层级，计算节点显示模板名称。

## 3. 用例 AC-003 正常工况执行

Given 已存在步进炉计算节点和正常输入样例。

When 用户发起执行。

Then 执行状态为 `SUCCESS`，结果 `feasible=true`，表里温差小于等于 5 ℃。

## 4. 用例 AC-004 不可行工况执行

Given 已存在停留时间不足的输入样例。

When 用户发起执行。

Then 执行状态为 `SUCCESS`，结果 `feasible=false`，返回超限值和建议。

## 5. 用例 AC-005 参数错误

Given 用户输入目标温度超出模板范围。

When 用户发起执行。

Then API 返回 `PARAM_INVALID`，页面显示字段错误。

## 6. 用例 AC-006 审批通过

Given 已存在一次成功执行。

When 普通计算人员提交审批，审核人审批通过。

Then 审批状态变为 `APPROVED`，审批日志包含 submit 和 approve。

## 7. 用例 AC-007 正式报告

Given 已存在审批通过的执行。

When 用户生成正式报告。

Then 报告状态为 `OFFICIAL`，报告编号符合 `RPT-{yyyyMMdd}-{sequence}`。

## 8. 用例 AC-008 横向对比

Given 已存在两个 `temp_profile` 类型执行结果。

When 用户创建对比组。

Then 对比页展示两个结果的核心输出字段。

## 9. 用例 AC-009 AI 联合分析

Given 已存在同一设备的执行结果、现场反馈、审图单、技术附件和图纸目录。

When 用户以“装出钢机”为设备名称发起 AI 联合分析。

Then 系统调用大模型 API 或演示回退，并按物质流、能量流、信息流展示风险点、矛盾点和建议。

## 10. 用例 AC-010 权限控制

Given 只读用户登录。

When 打开模板管理页或调用创建模板 API。

Then 页面隐藏创建按钮，API 返回 `PERMISSION_DENIED`。

## 11. 用例 AC-011 项目资料批量录入

Given 已存在样例项目。

When 普通计算人员按项目批量录入现场反馈、审图单、技术附件、图纸目录。

Then API 返回创建数量 4，项目资料列表包含四类资料。

## 12. 工程验收

1. `pytest` 通过。
2. `python3 -m compileall app tests` 通过。
3. seed 数据可重复执行。
4. SQLite 启动后可完成 AC-001 到 AC-011。
