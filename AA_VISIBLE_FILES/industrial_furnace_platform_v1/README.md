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
7. 现场反馈、审图单、技术说明、图纸目录、材料表、专利等技术文档资料管理。
8. 项目资料 AI 问答，根据当前项目资料中的文字内容回答用户问题。
9. 按项目批量录入现场反馈、审图单、技术说明、图纸目录、材料表、专利等技术文档。
10. 项目管理专用录入、批量录入、候选名单和项目台账查询。
11. 计算名目管理专用创建、台账查询和软删除。
12. 权限分配：管理员可查看权限目录并为非管理员角色分配功能权限。
 13. `POST /api/artifacts/reparse-stored-files` 可对已落盘的历史附件重新解析，适用于 PDF、Excel、文本和图片元信息补录。

## 页面模块

1. 项目管理：单点录入、Excel 复制粘贴批量录入、项目名称/项目经理/企业/智能关键词查询。
2. 计算名目管理：按步进炉、辊底炉、环形炉分类创建计算项，支持台账和软删除。
3. 计算执行：项目选择、名目选择、计算树节点、工况输入和执行记录。
4. 横向对比、审批报告、数字孪生、项目资料、AI 问答保持独立导航入口。
5. 权限分配：按角色勾选功能权限，系统管理员固定拥有全部权限。

## AI API 配置

AI 问答支持并列调用多个模型并分别展示回答。未配置环境变量时，系统从当前项目资料中生成本地回答，便于开发测试。

服务启动时会自动读取项目根目录下的 `.env` 或 `.env.local`。如果工作区里存在腾讯云 `SecretId,SecretKey` CSV 附件，启动时也会自动补齐 `TENCENT_SECRET_ID` 和 `TENCENT_SECRET_KEY`。

如果希望在 AI 未配置时只显示提示文案，而不是启用本地规则问答，可增加：

```bash
export LOCAL_RULE_FALLBACK_MODE="hint"
```

```bash
# DeepSeek 或其它 OpenAI 兼容模型
export AI_API_URL="https://example.com/v1/chat/completions"
export AI_API_KEY="your-api-key"
export AI_MODEL="your-model-name"
export AI_PROVIDER_NAME="DeepSeek"

# Claude 原生 API
export CLAUDE_API_URL="https://api.anthropic.com/v1/messages"
export CLAUDE_API_KEY="your-claude-api-key"
export CLAUDE_MODEL="claude-3-5-sonnet-latest"
export CLAUDE_PROVIDER_NAME="Claude"

# 腾讯云或其它额外模型，默认按 OpenAI 兼容接口调用
export TENCENT_API_URL="https://example.com/v1/chat/completions"
export TENCENT_API_KEY="your-tencent-api-key"
export TENCENT_MODEL="your-tencent-model"
export TENCENT_PROVIDER_NAME="Tencent"

# 如果你手里是腾讯云凭证文件而不是现成 Bearer Key，可以先按下面名字保存
export TENCENT_SECRET_ID="your-secret-id"
export TENCENT_SECRET_KEY="your-secret-key"
```

界面会把每个模型的回答并列展示，并标明 `provider` 和 `model`。

腾讯云附件字段映射模板：

```text
CSV 列名 SecretId  -> 环境变量 TENCENT_SECRET_ID
CSV 列名 SecretKey -> 环境变量 TENCENT_SECRET_KEY
接口地址           -> 环境变量 TENCENT_API_URL
模型名称           -> 环境变量 TENCENT_MODEL
展示名称           -> 环境变量 TENCENT_PROVIDER_NAME
```

当前代码请求腾讯云时优先读取 `TENCENT_API_KEY`；如果未单独配置，会回退读取 `TENCENT_SECRET_KEY`。如果你的腾讯云网关要求额外签名，再在部署层把 `SecretId/SecretKey` 转成对应网关可接受的鉴权方式。

## LightRAG 可选检索增强

AI 问答支持可选的 `LightRAG` 检索增强层。启用后，系统会先按项目资料建立本地 `LightRAG` 索引，再把检索出的文本片段回灌给现有问答逻辑；参数表、时间类和结构化回答规则继续沿用现有实现。

当前接入面向 GitHub 主仓版本 `HKUDS/LightRAG`。PyPI 上的 `lightrag` 是另一套接口，当前项目不使用它。

```bash
export LIGHTRAG_ENABLED=true
export OPENAI_API_KEY="your-openai-api-key"

# 可选，优先加载 LightRAG 主仓源码目录
export LIGHTRAG_SOURCE_PATH="/path/to/LightRAG"

# 可选，给 LightRAG 单独指定兼容 OpenAI 网关；也可以直接复用现有 AI_API_URL / AI_API_KEY / AI_MODEL
export LIGHTRAG_API_URL="https://example.com/v1"
export LIGHTRAG_API_KEY="your-lightrag-api-key"
export LIGHTRAG_MODEL="your-chat-model"
export LIGHTRAG_EMBEDDING_MODEL="your-embedding-model"

# 可选，默认用 ! 跳过实体关系抽取，只保留 chunks 向量索引
export LIGHTRAG_PROCESS_OPTIONS="!"

# 可选，默认 naive；如果已完成图谱抽取，可再切到 mix / hybrid
export LIGHTRAG_QUERY_MODE="naive"

# 可选，默认使用项目目录下的 lightrag_storage
export LIGHTRAG_WORKING_DIR="/path/to/lightrag_storage"

# 如果已构建图谱，可再切到 mix / hybrid
```

索引目录按 `project_id + 资料签名` 隔离。默认配置优先走“只建 chunk 向量索引”的轻量模式，减少对图谱抽取阶段 LLM 的依赖。`LightRAG` 检索失败时，系统会自动回退到当前关键词检索逻辑。

如果 `AI_API_URL` 使用的是完整聊天接口地址，例如 `https://example.com/v1/chat/completions`，适配层会自动裁剪成 `https://example.com/v1` 作为 `LightRAG` 的 base URL。

## 权限示例

```bash
curl -H "X-Role: engineer" -X POST http://127.0.0.1:8000/api/seed
```
