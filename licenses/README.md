# 第三方许可证清单说明

## 如何更新

```bash
python scripts/generate_license_report.py
```

该命令读取 `requirements.txt`、`frontend/package-lock.json` 和 `frontend/src-tauri/Cargo.lock`，生成 `licenses/THIRD-PARTY-LICENSES.md`。

## 发布前核验要求

- 脚本不联网，不猜测许可证，缺失字段标为“需人工核实”。
- 发布前应逐项确认“需人工核实”的最终许可证，并确认是否需要随安装包附带其许可证正文或 NOTICE。
- 对于 Python 依赖：运行 `pip show <包名>` 确认 `License` 字段。
- 对于 npm 包：检查 `node_modules/<包名>/package.json` 的 `license` 字段。
- 对于 Rust crate：检查 crates.io 页面或 `Cargo.toml` 的 `license` 字段。