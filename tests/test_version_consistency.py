"""版本号一致性契约测试（v0.1.8 plan 2）。

验证项目中三处版本号声明保持一致，防止版本号漂移（规范文档 8.3 节）。
三处来源：
    1. pyproject.toml 的 project.version（打包元数据）
    2. ui/main_window.py 的 _APP_VERSION（运行时显示给用户）
    3. installer.iss 的 #define MyAppVersion 与 OutputBaseFilename（安装包文件名）

任一处版本号更新时，其余两处必须同步更新，否则本测试失败。
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from ui.main_window import _APP_VERSION

# 项目根目录
_PROJECT_ROOT = Path(__file__).parent.parent

# 三处版本号来源文件
_PYPROJECT_PATH = _PROJECT_ROOT / "pyproject.toml"
_INSTALLER_PATH = _PROJECT_ROOT / "installer.iss"

# installer.iss 中 #define MyAppVersion "x.y.z" 的捕获正则
# v0.2.1：支持 ISPP 守卫块内的缩进 #define（如 "  #define MyAppVersion ..."）
_INSTALLER_DEFINE_RE = re.compile(r'^\s*#define\s+MyAppVersion\s+"([^"]+)"', re.MULTILINE)
# installer.iss 中 OutputBaseFilename=XieFengShiYing_Setup_v<version> 的捕获正则
# v0.2.1：支持 ISPP 变量引用 {#MyAppVersion}（CI 注入）与直接版本号（回退兼容）两种形态
_INSTALLER_OUTPUT_RE = re.compile(r"^OutputBaseFilename=XieFengShiYing_Setup_v(\S+)", re.MULTILINE)


def _read_pyproject_version() -> str:
    """从 pyproject.toml 读取 project.version。"""
    with _PYPROJECT_PATH.open("rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


def _read_installer_define_version() -> str:
    """从 installer.iss 读取 #define MyAppVersion 的值。"""
    text = _INSTALLER_PATH.read_text(encoding="utf-8")
    match = _INSTALLER_DEFINE_RE.search(text)
    assert match is not None, "installer.iss 缺少 #define MyAppVersion 行"
    return match.group(1)


def _read_installer_output_version() -> str:
    """从 installer.iss 读取 OutputBaseFilename 中的版本号。

    v0.2.1：OutputBaseFilename 现使用 ISPP 变量引用 ``{#MyAppVersion}``，
    本函数将其解析为 ``#define MyAppVersion`` 的实际值，保持与历史一致的
    纯版本号返回（如 ``0.2.0``），供一致性断言使用。
    """
    text = _INSTALLER_PATH.read_text(encoding="utf-8")
    match = _INSTALLER_OUTPUT_RE.search(text)
    assert match is not None, "installer.iss 缺少 OutputBaseFilename 行"
    raw = match.group(1)
    # ISPP 变量引用 {#MyAppVersion} -> 解析为 #define MyAppVersion 的值
    if raw.startswith("{#") and raw.endswith("}"):
        return _read_installer_define_version()
    return raw


class TestVersionConsistency:
    """三处版本号一致性测试（v0.1.8 plan 2 / 规范 8.3 节）。"""

    def test_pyproject_version_format(self) -> None:
        """pyproject.toml 版本号符合语义化版本 x.y.z 格式。"""
        version = _read_pyproject_version()
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"版本号格式非法: {version}"

    def test_ui_version_format(self) -> None:
        """ui/main_window.py _APP_VERSION 符合语义化版本 x.y.z 格式。"""
        assert re.fullmatch(r"\d+\.\d+\.\d+", _APP_VERSION), f"版本号格式非法: {_APP_VERSION}"

    def test_pyproject_equals_ui(self) -> None:
        """pyproject.toml 与 ui/main_window.py 版本号一致。"""
        assert _read_pyproject_version() == _APP_VERSION

    def test_installer_define_equals_ui(self) -> None:
        """installer.iss #define MyAppVersion 与 UI 版本号一致。"""
        assert _read_installer_define_version() == _APP_VERSION

    def test_installer_output_filename_equals_ui(self) -> None:
        """installer.iss OutputBaseFilename 中的版本号与 UI 版本号一致。"""
        assert _read_installer_output_version() == _APP_VERSION

    def test_all_three_sources_equal(self) -> None:
        """三处版本号（pyproject / UI / installer）完全一致。"""
        pyproject_version = _read_pyproject_version()
        installer_define = _read_installer_define_version()
        installer_output = _read_installer_output_version()
        assert pyproject_version == _APP_VERSION == installer_define == installer_output
