"""UI 层包。

导出主窗口与 UI 组件。具体页面功能在 v0.0.8 实现。
"""

from __future__ import annotations

from ui.error_handler import ERROR_MAPPING, ErrorHandler, ErrorInfo
from ui.main_window import MainWindow

__all__ = ["MainWindow", "ErrorHandler", "ErrorInfo", "ERROR_MAPPING"]
