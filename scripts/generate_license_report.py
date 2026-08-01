"""Generate a conservative dependency license inventory from lock files.

The report deliberately does not infer licenses from package names. Missing or
unavailable metadata is listed for manual verification instead.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

_PYTHON_DEPENDENCY_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*(?:[<>=!~].*)?$", re.MULTILINE)
_CARGO_PACKAGE_RE = re.compile(
    r'^\[\[package\]\]\s*\nname\s*=\s*"([^"]+)"\s*\nversion\s*=\s*"([^"]+)"',
    re.MULTILINE,
)


def _read_python_dependencies(root: Path) -> list[str]:
    path = root / "requirements.txt"
    if not path.exists():
        return []
    dependencies: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        match = _PYTHON_DEPENDENCY_RE.match(line)
        if match:
            dependencies.append(match.group(1))
    return sorted(set(dependencies), key=str.casefold)


def _read_npm_packages(root: Path) -> list[tuple[str, str, str]]:
    path = root / "frontend" / "package-lock.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    packages = data.get("packages", {})
    result: list[tuple[str, str, str]] = []
    for package_path, metadata in packages.items():
        if not package_path.startswith("node_modules/"):
            continue
        name = package_path.removeprefix("node_modules/")
        if not isinstance(metadata, dict):
            metadata = {}
        result.append(
            (
                name,
                str(metadata.get("version", "unknown")),
                str(metadata.get("license", "需人工核实")),
            )
        )
    return sorted(result, key=lambda item: item[0].casefold())


def _read_rust_crates(root: Path) -> list[tuple[str, str]]:
    path = root / "frontend" / "src-tauri" / "Cargo.lock"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return sorted(_CARGO_PACKAGE_RE.findall(text), key=lambda item: item[0].casefold())


def build_report(root: Path, generated_at: str | None = None) -> str:
    """Build a Markdown report without making license assumptions."""
    generated_at = generated_at or datetime.now(UTC).date().isoformat()
    python_dependencies = _read_python_dependencies(root)
    npm_packages = _read_npm_packages(root)
    rust_crates = _read_rust_crates(root)

    lines = [
        "# 第三方依赖许可证清单",
        "",
        f"> 生成日期：{generated_at}。本清单是工程审计辅助材料，不构成完整法律意见。",
        "> 许可证缺失或未从锁文件自动发现的项目统一标为“需人工核实”，不得据此推断许可证。",
        "",
        "## 输入文件",
        "",
        "- `requirements.txt`（Python 直接依赖约束）",
        "- `frontend/package-lock.json`（npm 锁定包及许可证字段）",
        "- `frontend/src-tauri/Cargo.lock`（Rust 锁定 crate；许可证需查 crate 元数据）",
        "",
        "## Python dependencies",
        "",
        "| 包 | 版本/许可证状态 | 来源 |",
        "| --- | --- | --- |",
    ]
    for dependency in python_dependencies:
        lines.append(
            f"| `{dependency}` | 需人工核实（从 pip show 或包元数据确认） | `requirements.txt` |"
        )
    if not python_dependencies:
        lines.append("| （未发现） | — | `requirements.txt` |")

    lines.extend(
        [
            "",
            "## npm dependencies",
            "",
            "| 包 | 锁定版本 | license 字段 |",
            "| --- | --- | --- |",
        ]
    )
    for name, version, license_name in npm_packages:
        lines.append(f"| `{name}` | `{version}` | {license_name} |")
    if not npm_packages:
        lines.append("| （未发现） | — | 需人工核实 |")

    lines.extend(
        [
            "",
            "## Rust crates",
            "",
            "| crate | 锁定版本 | 许可证状态 |",
            "| --- | --- | --- |",
        ]
    )
    for name, version in rust_crates:
        lines.append(f"| `{name}` | `{version}` | 需人工核实（从 crates.io 或 crate 源码确认） |")
    if not rust_crates:
        lines.append("| （未发现） | — | 需人工核实 |")

    lines.extend(
        [
            "",
            "## 发布前核验",
            "",
            "1. 对 Python 依赖查询实际安装包元数据，而不是只依据版本约束。",
            "2. 对 npm 包核对锁文件的 `license` 字段及其上游许可证文本。",
            "3. 对 Rust crate 查询 crates.io 或 crate 源码中的许可证和 NOTICE。",
            "4. 将需要随发布包提供的版权、许可证和 NOTICE 文件一并保留。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="报告输出路径，默认是 licenses/THIRD-PARTY-LICENSES.md",
    )
    args = parser.parse_args()
    output = args.output or args.root / "licenses" / "THIRD-PARTY-LICENSES.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_report(args.root), encoding="utf-8")
    print(f"许可证清单已写入 {output}")


if __name__ == "__main__":
    main()
