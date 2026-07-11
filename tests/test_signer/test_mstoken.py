"""msToken 生成单元测试。

测试内容：
    - 格式校验（长度/字符集）
    - 随机性（连续 1000 次无重复）
    - 异常分支（随机数生成失败抛出 SignError）
"""

from __future__ import annotations

import base64
import string
from unittest.mock import patch

import pytest

from crawlers.exceptions import SignError
from crawlers.signer import mstoken as mstoken_module
from crawlers.signer.mstoken import MsTokenGenerator

pytestmark = pytest.mark.signer


class TestMsTokenFormat:
    """格式校验。"""

    def test_non_empty(self, mstoken_generator: MsTokenGenerator) -> None:
        """输出为非空字符串。"""
        result = mstoken_generator.generate()
        assert result
        assert isinstance(result, str)

    def test_length(self, mstoken_generator: MsTokenGenerator) -> None:
        """输出长度约为 172 字符（128 字节 base64 编码）。"""
        result = mstoken_generator.generate()
        assert len(result) == 172

    def test_is_valid_base64(self, mstoken_generator: MsTokenGenerator) -> None:
        """输出为合法 base64 字符串。"""
        result = mstoken_generator.generate()
        decoded = base64.b64decode(result)
        assert len(decoded) == 128

    def test_charset(self, mstoken_generator: MsTokenGenerator) -> None:
        """输出字符集为标准 base64 字符集。"""
        result = mstoken_generator.generate()
        valid_chars = set(string.ascii_letters + string.digits + "+/=")
        assert all(c in valid_chars for c in result)


class TestMsTokenRandomness:
    """随机性测试。"""

    def test_consecutive_calls_different(self, mstoken_generator: MsTokenGenerator) -> None:
        """连续两次调用产生不同值。"""
        result1 = mstoken_generator.generate()
        result2 = mstoken_generator.generate()
        assert result1 != result2

    def test_1000_calls_no_duplicate(self, mstoken_generator: MsTokenGenerator) -> None:
        """连续调用 1000 次无重复值。"""
        results = {mstoken_generator.generate() for _ in range(1000)}
        assert len(results) == 1000


class TestMsTokenCustomLength:
    """自定义字节长度测试。"""

    def test_custom_byte_length(self) -> None:
        """自定义字节长度生效。"""
        generator = MsTokenGenerator(byte_length=64)
        result = generator.generate()
        decoded = base64.b64decode(result)
        assert len(decoded) == 64

    def test_default_byte_length(self) -> None:
        """默认字节长度为 128。"""
        generator = MsTokenGenerator()
        result = generator.generate()
        decoded = base64.b64decode(result)
        assert len(decoded) == 128


class TestMsTokenErrorHandling:
    """异常分支测试（覆盖 except 块）。"""

    def test_token_bytes_failure_raises_sign_error(self) -> None:
        """secrets.token_bytes 抛出异常时，generate 抛出 SignError。"""
        generator = MsTokenGenerator()
        original_error = RuntimeError("entropy source unavailable")
        with (
            patch.object(mstoken_module.secrets, "token_bytes", side_effect=original_error),
            pytest.raises(SignError) as exc_info,
        ):
            generator.generate()
        assert "msToken 生成失败" in str(exc_info.value)
        assert exc_info.value.algorithm == "mstoken"
        assert exc_info.value.__cause__ is original_error

    def test_b64encode_failure_raises_sign_error(self) -> None:
        """base64.b64encode 抛出异常时，generate 抛出 SignError。"""
        generator = MsTokenGenerator()
        original_error = TypeError("encoding error")
        with (
            patch.object(mstoken_module.base64, "b64encode", side_effect=original_error),
            pytest.raises(SignError) as exc_info,
        ):
            generator.generate()
        assert "msToken 生成失败" in str(exc_info.value)
        assert exc_info.value.algorithm == "mstoken"
        assert exc_info.value.__cause__ is original_error

    def test_negative_byte_length_raises_sign_error(self) -> None:
        """负数字节长度导致 token_bytes 抛出异常时，generate 抛出 SignError。"""
        generator = MsTokenGenerator(byte_length=-1)
        with pytest.raises(SignError) as exc_info:
            generator.generate()
        assert exc_info.value.algorithm == "mstoken"
        assert exc_info.value.__cause__ is not None
