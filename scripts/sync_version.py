#!/usr/bin/env python3
"""版本号自动同步脚本。

支持三种模式：
  sync - 同步 pyproject.toml 的版本号到其他文件
  check - 检查所有版本号是否一致
  validate-tag - 验证版本号与 git tag 是否一致
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from typing import NamedTuple

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


class VersionConfig(NamedTuple):
    """版本号文件配置。"""

    file_path: Path
    pattern: re.Pattern[str]
    replacement_template: str
    description: str


# 版本号文件配置清单（6 个文件）
VERSION_CONFIGS = [
    VersionConfig(
        file_path=PROJECT_ROOT / "pyproject.toml",
        pattern=re.compile(r'^version = "([0-9.]+)"', re.MULTILINE),
        replacement_template='version = "{version}"',
        description="Python 项目配置",
    ),
    VersionConfig(
        file_path=PROJECT_ROOT / "backend" / "app.py",
        pattern=re.compile(r'version="([0-9.]+)"'),
        replacement_template='version="{version}"',
        description="FastAPI 后端版本",
    ),
    VersionConfig(
        file_path=PROJECT_ROOT / "frontend" / "package.json",
        pattern=re.compile(r'"version":\s*"([0-9.]+)"'),
        replacement_template='"version": "{version}"',
        description="前端 npm 配置",
    ),
    VersionConfig(
        file_path=PROJECT_ROOT / "frontend" / "src-tauri" / "tauri.conf.json",
        pattern=re.compile(r'"version":\s*"([0-9.]+)"'),
        replacement_template='"version": "{version}"',
        description="Tauri 应用配置",
    ),
    VersionConfig(
        file_path=PROJECT_ROOT / "frontend" / "src-tauri" / "src" / "lib.rs",
        pattern=re.compile(r'"(0\.[0-9.]+)"\.to_string\(\)'),
        replacement_template='"{version}".to_string()',
        description="Rust 版本获取函数",
    ),
    VersionConfig(
        file_path=PROJECT_ROOT / "installer.iss",
        pattern=re.compile(r'#define MyAppVersion "([0-9.]+)"'),
        replacement_template='#define MyAppVersion "{version}"',
        description="Windows 安装程序配置",
    ),
]


def get_version_from_pyproject() -> str:
    """从 pyproject.toml 读取版本号。"""
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


def extract_version(file_path: Path, pattern: re.Pattern[str]) -> str | None:
    """从文件中提取版本号。"""
    try:
        content = file_path.read_text(encoding="utf-8")
        match = pattern.search(content)
        return match.group(1) if match else None
    except Exception as e:
        print(f"❌ 读取文件失败 {file_path}: {e}", file=sys.stderr)
        return None


def sync_version(target_version: str) -> bool:
    """同步版本号到所有文件。

    Args:
        target_version: 目标版本号 (e.g., "0.3.2")

    Returns:
        是否成功同步
    """
    # 验证版本号格式
    if not re.fullmatch(r"\d+\.\d+\.\d+", target_version):
        print(f"❌ 版本号格式非法: {target_version}", file=sys.stderr)
        return False

    print(f"正在同步版本号到 {target_version}...\n")

    success_count = 0
    for config in VERSION_CONFIGS:
        if not config.file_path.exists():
            print(f"❌ {config.description}: 文件不存在 {config.file_path}")
            continue

        try:
            content = config.file_path.read_text(encoding="utf-8")
            new_content = config.pattern.sub(
                config.replacement_template.format(version=target_version),
                content,
                count=1,
            )

            if new_content == content:
                print(f"⚠️  {config.description}: 未找到版本号标记")
                continue

            config.file_path.write_text(new_content, encoding="utf-8")
            print(f"✅ {config.description}")
            success_count += 1
        except Exception as e:
            print(f"❌ {config.description}: {e}", file=sys.stderr)

    print(f"\n成功同步 {success_count}/{len(VERSION_CONFIGS)} 个文件到版本 {target_version}")
    return success_count == len(VERSION_CONFIGS)


def check_versions() -> tuple[bool, dict[str, str | None]]:
    """检查所有版本号是否一致。

    Returns:
        (是否一致, {文件名: 版本号})
    """
    versions = {}
    for config in VERSION_CONFIGS:
        version = extract_version(config.file_path, config.pattern)
        versions[config.description] = version

    # 获取非 None 的版本号集合
    valid_versions = {v for v in versions.values() if v is not None}

    is_consistent = len(valid_versions) <= 1
    return is_consistent, versions


def print_version_report(versions: dict[str, str | None]) -> None:
    """打印版本号检查报告。"""
    print("\n📋 版本号检查报告:\n")
    for desc, version in versions.items():
        if version is None:
            print(f"  ❌ {desc}: 未找到版本号")
        else:
            print(f"  ✅ {desc}: {version}")


def validate_tag(tag: str) -> bool:
    """验证版本号与 git tag 是否一致。

    Args:
        tag: git tag (e.g., "v0.3.2" or "0.3.2")

    Returns:
        是否一致
    """
    # 去掉 v 前缀
    tag_version = tag.lstrip("v")

    if not re.fullmatch(r"\d+\.\d+\.\d+", tag_version):
        print(f"❌ Tag 版本号格式非法: {tag_version}", file=sys.stderr)
        return False

    print(f"验证版本号与 tag {tag} (版本: {tag_version}) 的一致性...\n")

    is_consistent, versions = check_versions()
    print_version_report(versions)

    # 检查每个版本是否都与 tag 匹配
    mismatches = []
    for desc, version in versions.items():
        if version is None:
            mismatches.append((desc, "未找到版本号", tag_version))
        elif version != tag_version:
            mismatches.append((desc, version, tag_version))

    if mismatches:
        print("\n❌ 版本号检查失败！存在不匹配:\n")
        for desc, actual, expected in mismatches:
            print(f"  {desc}:")
            print(f"    实际: {actual}")
            print(f"    期望: {expected}\n")
        return False

    print(f"\n✅ 所有版本号与 tag {tag} 一致")
    return True


def main() -> int:
    """主函数。"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  python sync_version.py sync         # 同步 pyproject.toml 版本号到其他文件")
        print("  python sync_version.py check        # 检查版本号一致性")
        print("  python sync_version.py validate-tag <tag>  # 验证与 git tag 一致性")
        return 1

    mode = sys.argv[1]

    if mode == "sync":
        version = get_version_from_pyproject()
        success = sync_version(version)
        return 0 if success else 1

    elif mode == "check":
        is_consistent, versions = check_versions()
        print_version_report(versions)
        if not is_consistent:
            print("\n❌ 版本号不一致")
            return 1
        print("\n✅ 所有版本号一致")
        return 0

    elif mode == "validate-tag":
        if len(sys.argv) < 3:
            print("用法: python sync_version.py validate-tag <tag>", file=sys.stderr)
            return 1
        tag = sys.argv[2]
        success = validate_tag(tag)
        return 0 if success else 1

    else:
        print(f"❌ 未知模式: {mode}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
