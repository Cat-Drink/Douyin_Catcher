"""UI 页面包。

导出 4 个页面占位类。所有页面继承 QWidget 并实现统一 refresh() 接口。
"""

from __future__ import annotations

from ui.pages.cookie_page import CookiePage
from ui.pages.download_page import DownloadPage
from ui.pages.fetch_page import FetchPage
from ui.pages.onboarding_page import OnboardingPage
from ui.pages.settings_page import SettingsPage

__all__ = [
    "CookiePage",
    "DownloadPage",
    "FetchPage",
    "OnboardingPage",
    "SettingsPage",
]
