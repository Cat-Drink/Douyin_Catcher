"""端到端集成测试 fixtures。

提供真实 Cookie 读取、临时下载目录、临时数据库、Cookie 痕迹清除等 fixtures。
所有端到端测试用 @pytest.mark.integration 标记，CI 默认跳过。

Cookie 使用规范（严格遵循设计文档 9.1 节、规范文档 6.1 节）：
    - 真实 Cookie 由用户提供，存放在项目根目录的 .test_cookie.txt 文件
    - 该文件已被 .gitignore 排除，绝不入库
    - 测试全流程完成后必须清除 Cookie 痕迹

运行方式::

    # 需先在项目根目录创建 .test_cookie.txt，写入有效抖音 Cookie
    pytest -m integration

    # 单独运行某个场景
    pytest tests/test_e2e/test_single_video.py -m integration
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app import database

# 项目根目录
_PROJECT_ROOT = Path(__file__).parent.parent.parent

# Cookie / 测试数据文件路径（均已被 .gitignore 排除）
_COOKIE_PATH = _PROJECT_ROOT / ".test_cookie.txt"
_SEC_USER_ID_PATH = _PROJECT_ROOT / ".test_sec_user_id.txt"
_AWEME_ID_PATH = _PROJECT_ROOT / ".test_aweme_id.txt"
_IMAGE_SET_AWEME_ID_PATH = _PROJECT_ROOT / ".test_image_set_aweme_id.txt"
_LONG_VIDEO_AWEME_ID_PATH = _PROJECT_ROOT / ".test_long_video_aweme_id.txt"

# 标记所有端到端测试为 integration（CI 默认跳过）
pytestmark = pytest.mark.integration


def _read_text_file(path: Path) -> str | None:
    """读取文件内容，文件不存在或为空时返回 None。"""
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8").strip()
    return content or None


@pytest.fixture(scope="session")
def real_cookie() -> str:
    """返回真实抖音 Cookie 字符串，未配置时跳过。

    从项目根目录的 .test_cookie.txt 读取（已被 .gitignore 排除）。
    """
    cookie = _read_text_file(_COOKIE_PATH)
    if cookie is None:
        pytest.skip("未找到 .test_cookie.txt，端到端测试跳过（需用户提供 Cookie）")
    return cookie


@pytest.fixture(scope="session")
def real_sec_user_id() -> str:
    """返回真实 sec_user_id，未配置时跳过。

    用于用户主页抓取测试，从 .test_sec_user_id.txt 读取。
    """
    sec_user_id = _read_text_file(_SEC_USER_ID_PATH)
    if sec_user_id is None:
        pytest.skip("未找到 .test_sec_user_id.txt，主页抓取测试跳过")
    return sec_user_id


@pytest.fixture(scope="session")
def real_aweme_id() -> str:
    """返回真实 aweme_id（单视频），未配置时跳过。

    用于单视频下载测试，从 .test_aweme_id.txt 读取。
    """
    aweme_id = _read_text_file(_AWEME_ID_PATH)
    if aweme_id is None:
        pytest.skip("未找到 .test_aweme_id.txt，单视频测试跳过")
    return aweme_id


@pytest.fixture(scope="session")
def real_image_set_aweme_id() -> str:
    """返回真实 aweme_id（图集），未配置时跳过。

    用于图集下载测试，从 .test_image_set_aweme_id.txt 读取。
    """
    aweme_id = _read_text_file(_IMAGE_SET_AWEME_ID_PATH)
    if aweme_id is None:
        pytest.skip("未找到 .test_image_set_aweme_id.txt，图集测试跳过")
    return aweme_id


@pytest.fixture(scope="session")
def real_long_video_aweme_id() -> str:
    """返回真实 aweme_id（长视频），未配置时跳过。

    用于长视频下载测试，从 .test_long_video_aweme_id.txt 读取。
    """
    aweme_id = _read_text_file(_LONG_VIDEO_AWEME_ID_PATH)
    if aweme_id is None:
        pytest.skip("未找到 .test_long_video_aweme_id.txt，长视频测试跳过")
    return aweme_id


@pytest.fixture
def tmp_download_dir(tmp_path: Path) -> Path:
    """返回临时下载目录，测试后自动清理。

    使用 pytest 内置 tmp_path，测试结束自动删除。
    """
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    return download_dir


@pytest.fixture
def clean_db(tmp_path: Path) -> sqlite3.Connection:
    """返回临时文件 SQLite 数据库连接（已初始化），测试后关闭。

    每个测试函数独立数据库，互不污染。
    """
    db_path = tmp_path / "test.db"
    conn = database.get_connection(db_path)
    database.init_db(conn)
    yield conn
    conn.close()


@pytest.fixture(scope="session", autouse=True)
def cleanup_cookie_traces() -> None:
    """session 结束后自动清除 Cookie 痕迹。

    严格遵循规范：测试后所有 Cookie 痕迹必须清除。
    清除内容：
    - .test_cookie.txt
    - .test_sec_user_id.txt
    - .test_aweme_id.txt
    - .test_image_set_aweme_id.txt
    - .test_long_video_aweme_id.txt
    """
    yield
    # session 结束后清理 Cookie 文件
    for path in (
        _COOKIE_PATH,
        _SEC_USER_ID_PATH,
        _AWEME_ID_PATH,
        _IMAGE_SET_AWEME_ID_PATH,
        _LONG_VIDEO_AWEME_ID_PATH,
    ):
        if path.exists():
            path.unlink()
