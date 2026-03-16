# MCP/Skills 架构师 - 前端（v0-ai Next.js）

与后端 API 已对接：输入 Idea 调用 `POST /api/recommend`，展示推荐工具与路线图，反馈调用 `POST /api/feedback`。

## 对接说明

- **推荐**：`POST /api/recommend`，body `{ query, top_k: 12 }`，返回 `request_id`、`retrieved`、`reasoning`、`metrics`。
- **反馈**：`POST /api/feedback`，body `{ request_id, is_useful, clicked_tool_id, action_type }`。
- 开发时通过 `next.config.mjs` 的 **rewrites** 将 `/api`、`/health` 代理到后端（默认 `http://127.0.0.1:8000`）。前端使用相对路径 `/api/...` 即可。

可选：在 `frontend` 下新建 `.env.local`，设置 `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`（或你的后端地址），用于改写代理目标。

## 启动

**先启动后端**（项目根目录）：

```bash
.\.venv\Scripts\activate
python -m uvicorn api:app --reload --port 8000
```

**再启动前端**：

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 http://localhost:3000 。若项目路径含 `&` 导致 `npm run dev` 报错，可使用：

```bash
node node_modules/next/dist/bin/next dev
```
