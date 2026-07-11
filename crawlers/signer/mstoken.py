"""msToken 随机生成模块。

msToken 是抖音 Web 请求中的随机性签名参数，无需服务端校验输入，
但长度与字符集需符合抖音前端规律。

实现方式：使用 secrets 模块（密码学安全的随机数生成器）生成随机字节，
再编码为 base64 字符串。不依赖时间戳或可预测因子，确保随机性。

输入/输出契约：
    - 输入：无（纯随机生成）
    - 输出：msToken 字符串（约 170+ 字符的 base64 编码）
    - 每次调用产生不同的随机值
"""

from __future__ import annotations

import base64
import secrets

from crawlers.exceptions import SignError

# msToken 随机字节数（128 字节 → base64 编码后约 172 字符）
# 来源：抖音 Web 前端实际请求样本中观察到的 msToken 长度
_MSTOKEN_RANDOM_BYTES: int = 128


class MsTokenGenerator:
    """msToken 随机生成器。

    使用密码学安全的随机数生成器（secrets）生成随机字节，
    再编码为 base64 字符串。每次调用产生不同的随机值。

    msToken 在抖音 Web 请求中为随机生成的 base64 风格字符串，
    长度约 170+ 字符，字符集为标准 base64 字符集。
    """

    def __init__(self, byte_length: int = _MSTOKEN_RANDOM_BYTES) -> None:
        """初始化 msToken 生成器。

        参数:
            byte_length: 随机字节数，默认 128（base64 编码后约 172 字符）。
        """
        self._byte_length = byte_length

    def generate(self) -> str:
        """生成 msToken 参数值。

        使用 secrets.token_bytes 生成密码学安全的随机字节，
        再编码为 base64 字符串。

        返回:
            msToken 字符串（base64 编码，约 170+ 字符）。

        异常:
            SignError: 随机数生成失败。
        """
        try:
            random_bytes = secrets.token_bytes(self._byte_length)
            return base64.b64encode(random_bytes).decode("ascii")
        except Exception as e:
            raise SignError(f"msToken 生成失败: {e}", algorithm="mstoken") from e
