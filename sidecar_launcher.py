"""Sidecar 入口 — 启动 FastAPI 后端服务。

被 PyInstaller 打包为单一可执行文件，供 Tauri 桌面壳作为 sidecar 启动。
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",
        port=18989,
        log_level="info",
    )