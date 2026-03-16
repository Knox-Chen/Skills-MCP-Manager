# 后端测试说明

本文档说明如何测试整个后端（推荐接口、反馈接口、埋点与评估日志模块）。

---

## 一、前置条件

- Python 3.10+，已安装项目依赖：`pip install -r requirements.txt`
- **完整联调测试**需要配置 `.env`（Pinecone、豆包 API），否则只跑「不依赖真实服务的测试」

---

## 二、自动化测试（不启动服务、不连 Pinecone/豆包）

使用 **pytest** 对 API 与评估逻辑做单元/集成测试，**mock 掉 recommend()**，不加载向量模型、不访问 Pinecone/LLM。

### 1. 安装测试依赖

```bash
cd "d:\skill & MCP Manager"
pip install -r requirements.txt   # 已含 pytest、httpx
# 或仅测试依赖
pip install pytest httpx fastapi
```

### 2. 运行所有测试

```bash
# 项目根目录下执行（推荐使用项目 venv）
python -m pytest tests/ -v

# 或先激活 venv 再执行
# Windows:  .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pytest tests/ -v
```

### 3. 测试内容概览

| 测试文件 | 说明 |
|----------|------|
| `tests/test_api_and_analytics.py` | FastAPI 客户端：健康检查、POST /api/recommend（mock recommend）、POST /api/feedback，校验埋点写入临时 `analytics_v1.jsonl` |
| `tests/test_evaluate_analytics.py` | 评估脚本逻辑：读 JSONL、统计推荐数/反馈数/采纳率，边界情况（空文件、仅 recommend、仅 feedback） |

---

## 三、手动测试（真实服务）

在已配置 `.env` 的前提下，可对真实推荐与埋点做端到端验证。

### 1. 启动后端

```bash
cd "d:\skill & MCP Manager"
python -m uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

### 2. 健康检查

```bash
curl http://127.0.0.1:8000/health
# 期望: {"status":"ok"}
```

### 3. 调用推荐接口（会写埋点）

```bash
curl -X POST http://127.0.0.1:8000/api/recommend ^
  -H "Content-Type: application/json" ^
  -d "{\"query\": \"我想做一个自动读 PDF 并总结到 Notion 的 Agent\", \"top_k\": 12}"
```

Windows PowerShell 示例：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/recommend" -Method Post -ContentType "application/json" -Body '{"query":"我想做一个自动读 PDF 并总结到 Notion 的 Agent","top_k":12}'
```

记下返回的 `request_id`，用于下一步反馈。

### 4. 调用反馈接口

将下面的 `REQUEST_ID` 换成上一步返回的 `request_id`：

```bash
curl -X POST http://127.0.0.1:8000/api/feedback ^
  -H "Content-Type: application/json" ^
  -d "{\"request_id\": \"REQUEST_ID\", \"is_useful\": true, \"clicked_tool_id\": \"\", \"action_type\": \"click\"}"
```

### 5. 校验埋点并跑评估

- 埋点文件位置：项目根目录下的 `analytics_v1.jsonl`。
- 每行一条 JSON：`event_type` 为 `recommend` 或 `feedback`，含 `request_id`、`query`、`metrics` 等。

按需运行评估脚本：

```bash
python evaluate_analytics.py
# 或指定日志路径
python evaluate_analytics.py analytics_v1.jsonl
```

确认输出中有「总推荐次数」「方案采纳率」等与本次操作一致。

---

## 四、仅测推荐逻辑（CLI，不经过 API）

不启动 API，直接测 `recommend.py`（会连 Pinecone 与豆包，需配置 `.env`）：

```bash
python recommend.py "我想做一个自动读 PDF 并总结到 Notion 的 Agent"
```

控制台会打印推荐结果与 `metrics`（三阶段耗时、`hyde_length`、`top1_score`）。

---

## 五、测试清单速查

| 项目 | 命令/操作 |
|------|-----------|
| 自动化测试（mock，无需 .env） | `pytest tests/ -v` |
| 启动 API 服务 | `python -m uvicorn api:app --reload --port 8000` |
| 健康检查 | `curl http://127.0.0.1:8000/health` |
| 推荐接口 | `POST /api/recommend`，body: `{"query":"...", "top_k":12}` |
| 反馈接口 | `POST /api/feedback`，body: `request_id, is_useful, clicked_tool_id, action_type` |
| 评估日志（按需） | `python evaluate_analytics.py` |
| 推荐 CLI（真实服务） | `python recommend.py "你的 Idea"` |
