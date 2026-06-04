# 用户指令记忆

本文件记录了用户的指令、偏好和教导，用于在未来的交互中提供参考。

## 格式

### 用户指令条目
用户指令条目应遵循以下格式：

[用户指令摘要]
- Date: [YYYY-MM-DD]
- Context: [提及的场景或时间]
- Instructions:
  - [用户教导或指示的内容，逐行描述]

### 项目知识条目
Agent 在任务执行过程中发现的条目应遵循以下格式：

[项目知识摘要]
- Date: [YYYY-MM-DD]
- Context: Agent 在执行 [具体任务描述] 时发现
- Category: [运维部署|构建方法|测试方法|排错调试|工作流协作|环境配置]
- Instructions:
  - [具体的知识点，逐行描述]

## 去重策略
- 添加新条目前，检查是否存在相似或相同的指令
- 若发现重复，跳过新条目或与已有条目合并
- 合并时，更新上下文或日期信息
- 这有助于避免冗余条目，保持记忆文件整洁

## 条目

V1 独立工程验证方法
- Date: 2026-06-04
- Context: Agent 在执行工业炉计算平台 V1 后端骨架开发时发现
- Category: 测试方法
- Instructions:
  - V1 独立工程位于 `/workspace/AA_VISIBLE_FILES/industrial_furnace_platform_v1`，右侧可见目录优先查看 `AA_VISIBLE_FILES`。
  - V1 工程验证命令为 `python3 -m compileall app tests` 和 `python3 -m pytest`。
  - V1 工程依赖安装命令为 `pip install --break-system-packages -r requirements.txt`。
