#!/usr/bin/env python3
"""统一入口：从环境变量 PORT 读取端口并启动服务（Railway 等云平台会注入 PORT）。"""
import os
import uvicorn
from api import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"[run] PORT env={os.environ.get('PORT', '(not set)')}, binding 0.0.0.0:{port}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port)
