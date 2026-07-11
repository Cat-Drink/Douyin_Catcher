# DouyinCatcher

抖音短视频（含图文、长视频）数据抓取的 Windows 桌面端应用，面向非技术用户。

## 设计来源

本项目参考 [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) 的设计思路，但核心功能（签名算法、链接解析、下载引擎）均为本项目的自研组件，不直接复用其代码，以降低外部依赖风险。

## 技术栈

- **UI 框架**：PySide6 (Qt)
- **爬虫语言**：Python + httpx[http2]（异步）
- **数据库**：SQLite（WAL 模式）
- **打包**：PyInstaller --onedir + Inno Setup

## 开发环境搭建

1. 安装 Python 3.11+
2. 创建并激活虚拟环境：

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. 安装开发依赖：

   ```powershell
   pip install -r requirements-dev.txt
   ```

4. 运行测试：

   ```powershell
   pytest
   ```

5. 代码规范检查：

   ```powershell
   ruff check .
   black --check .
   ```

## 目录结构概览

详见 `docs/superpowers/specs/2026-07-11-douyin-catcher-design.md` 第 8 节。

```
DouyinCatcher/
├── app/            # 数据层、配置、日志、Repository
├── ui/             # PySide6 界面
├── crawlers/       # 爬虫组件（签名、解析、HTTP）
├── downloader/     # 下载引擎
├── worker/         # 工作线程桥接
├── assets/         # 应用图标等资源
├── tests/          # 单元测试与集成测试
└── docs/           # 设计文档与实现计划
```

## License

MIT
