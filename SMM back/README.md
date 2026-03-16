# MCP/Skills 架构师 Agent

用户输入 Idea → 推荐 MCP/Skill 组合与全栈实现方案，支持埋点与方案采纳率评估。

## 快速开始：前后端联调

1. **启动后端**（项目根目录，需先配置 `.env`）：
   ```bash
   # 先激活 venv，再执行（若 uvicorn 未在 PATH，用 python -m 方式）
   .\.venv\Scripts\activate
   python -m uvicorn api:app --reload --port 8000
   ```

2. **启动前端**（Next.js，v0-ai 界面）：
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   浏览器访问 http://localhost:3000 ；前端通过 next.config 将 `/api` 代理到后端 8000 端口。若路径含 `&` 导致脚本报错，可执行：`node node_modules/next/dist/bin/next dev`

3. 在页面输入 Idea、点击「获取推荐」，即可看到推荐结果与反馈按钮；反馈会写入 `analytics_v1.jsonl` 用于采纳率统计。

更多说明见 [frontend/README.md](frontend/README.md)、[TESTING.md](TESTING.md)。

## 项目结构

- `api.py` - FastAPI 接口（/api/recommend、/api/feedback）
- `recommend.py` - 推荐逻辑（HyDE + 集成检索 + 豆包重排）
- `analytics_v1.py` - 埋点异步写入 analytics_v1.jsonl
- `evaluate_analytics.py` - 按需评估脚本（方案采纳率等）
- `frontend/` - React + Vite 前端（与后端 API 对接）
