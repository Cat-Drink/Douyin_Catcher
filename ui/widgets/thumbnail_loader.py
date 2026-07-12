"""缩略图异步加载器模块。

使用 ``QNetworkAccessManager`` 异步加载网络图片，不阻塞 UI 主线程。
加载完成通过信号回传 ``QPixmap``，加载失败保持占位图。

严格遵循 v0.0.8 计划文档 4.9 节（缩略图异步加载约束）。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)

from app.logger import get_logger

logger = get_logger(__name__)


class ThumbnailLoader(QObject):
    """缩略图异步加载器。

    使用 ``QNetworkAccessManager`` 发起异步 HTTP GET 请求下载图片，
    下载完成通过 ``loaded`` 信号回传 ``QPixmap``。

    信号:
        loaded: 图片加载完成，参数为 QPixmap（加载失败时为空 QPixmap）。
    """

    loaded = Signal(QPixmap)

    def __init__(self, parent: QObject | None = None) -> None:
        """初始化加载器。

        Args:
            parent: 父对象。
        """
        super().__init__(parent)
        self._nam: QNetworkAccessManager = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None

    def load(self, url: str, target_size: tuple[int, int] = (64, 64)) -> None:
        """异步加载图片。

        取消未完成的旧请求，发起新请求。
        加载完成后缩放至 ``target_size`` 并通过 ``loaded`` 信号回传。

        Args:
            url: 图片 URL。
            target_size: 目标尺寸 (width, height)。
        """
        self._target_size = target_size
        # 取消旧请求
        if self._reply is not None:
            self._reply.abort()
            self._reply.deleteLater()
            self._reply = None

        if not url:
            self.loaded.emit(QPixmap())
            return

        request = QNetworkRequest(QUrl(url))
        request.setHeader(
            QNetworkRequest.KnownHeaders.UserAgentHeader,
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        self._reply = self._nam.get(request)
        self._reply.finished.connect(self._on_finished)

    def _on_finished(self) -> None:
        """请求完成回调：解析图片数据，缩放，发射信号。"""
        if self._reply is None:
            return

        pixmap = QPixmap()
        if self._reply.error() == QNetworkReply.NetworkError.NoError:
            data = self._reply.readAll()
            if pixmap.loadFromData(data):
                pixmap = pixmap.scaled(
                    self._target_size[0],
                    self._target_size[1],
                    aspectMode=1,  # KeepAspectRatio
                    mode=1,  # SmoothTransformation
                )
            else:
                logger.warning("缩略图数据解析失败")
        else:
            logger.debug("缩略图加载失败: %s", self._reply.errorString())

        self._reply.deleteLater()
        self._reply = None
        self.loaded.emit(pixmap)

    def cancel(self) -> None:
        """取消未完成的请求。"""
        if self._reply is not None:
            self._reply.abort()
            self._reply.deleteLater()
            self._reply = None
