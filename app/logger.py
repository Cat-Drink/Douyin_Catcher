"""日志配置模块。

配置按天滚动的文件日志 + 控制台日志，保留 7 天。
供全应用通过 logging.getLogger(__name__) 使用。

使用约定：
- 应用入口 main.py 调用 setup_logger() 一次
- 其他模块用 `from app.logger import get_logger` + `logger = get_logger(__name__)`
"""

from __future__ import annotations

import logging
import logging.handlers

from app import config

# 日志格式与日期格式
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(level: int = logging.INFO) -> logging.Logger:
    """配置并返回根 logger。

    - 调用 config.ensure_app_dirs() 确保 LOG_DIR 存在
    - 创建 TimedRotatingFileHandler（按天滚动，保留 7 天）
    - 创建 StreamHandler 输出到控制台（开发期调试用）
    - 防止重复添加 handler：若根 logger 已有 handler 则先清空

    Args:
        level: 日志级别，默认 logging.INFO

    Returns:
        配置好的根 logger
    """
    # 确保日志目录存在
    config.ensure_app_dirs()

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 防止重复添加 handler：先清空已有 handler
    if root_logger.handlers:
        root_logger.handlers.clear()

    # 格式化器
    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # 文件 handler：按天滚动，午夜切割，保留 7 天
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(config.LOG_FILE),
        when="midnight",
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    # 控制台 handler（开发期调试用，打包后可移除）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """返回指定名称的 logger。

    供各模块调用 `logger = get_logger(__name__)`。

    Args:
        name: logger 名称，通常传 __name__

    Returns:
        logging.Logger 实例
    """
    return logging.getLogger(name)
