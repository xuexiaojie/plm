# 10 AI 编码计划

## 1. 执行原则

1. 每次只生成一个层级产物。
2. 每次生成前必须引用对应规格文件。
3. 每次生成后必须运行对应验证。
4. 规格与代码冲突时，以规格为准。

## 2. Prompt 分包

### 2.1 建模 Prompt

输入：`01-domain-model.md`、`02-database-schema.md`

输出：ORM 模型、迁移脚本、Pydantic Schema。

验证：`python3 -m compileall app`

### 2.2 初始化数据 Prompt

输入：`11-seed-data.md`

输出：seed 脚本。

验证：重复执行 seed 无重复数据错误。

### 2.3 执行器 Prompt

输入：`03-calc-item-template-schema.md`、`04-model-sample-data.md`、`05-executor-protocol.md`

输出：Python 执行器和三类 Mock 模型。

验证：正常、边界、不可行样例通过测试。

### 2.4 API Prompt

输入：`06-api-contract.md`、`12-permission-matrix.md`、`13-error-code-and-storage.md`

输出：FastAPI 路由和权限检查。

验证：API 测试通过。

### 2.5 页面 Prompt

输入：`07-page-requirements.md`

输出：轻量 HTML/JS 页面。

验证：页面流程可完成验收用例。

### 2.6 报告 Prompt

输入：`08-report-and-approval.md`

输出：报告生成、编号、状态流转。

验证：报告用例通过。

### 2.7 测试 Prompt

输入：`09-acceptance-cases.md`

输出：pytest 测试。

验证：全部测试通过。

## 3. 推荐实现顺序

1. ORM 与迁移。
2. Pydantic Schema。
3. seed 数据。
4. 执行器。
5. API。
6. 页面。
7. 报告审批。
8. 测试。
9. 操作说明。
