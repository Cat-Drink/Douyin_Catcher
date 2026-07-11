"""Signer 聚合接口单元测试。

测试内容：
    - sign() 返回含四个键的字典
    - generate_ms_token() / generate_verify_fp() 正常返回
    - 子算法失败时抛出 SignError
    - 默认 UA 与显式 UA 优先级
"""

from __future__ import annotations

import pytest

from crawlers.exceptions import SignError
from crawlers.signer import DEFAULT_USER_AGENT, Signer

pytestmark = pytest.mark.signer


class TestSignerSign:
    """sign() 方法测试。"""

    def test_returns_four_keys(self) -> None:
        """sign() 返回含 X-Bogus / a_bogus / msToken / verifyFp 四个键的字典。"""
        signer = Signer()
        result = signer.sign(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            {"aweme_id": "123", "aid": "6383"},
        )
        assert set(result.keys()) == {"X-Bogus", "a_bogus", "msToken", "verifyFp"}

    def test_all_values_non_empty(self) -> None:
        """所有签名值为非空字符串。"""
        signer = Signer()
        result = signer.sign(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            {"aweme_id": "123", "aid": "6383"},
        )
        for key, value in result.items():
            assert value, f"{key} 值为空"
            assert isinstance(value, str), f"{key} 值不是字符串"

    def test_xbogus_length_28(self) -> None:
        """X-Bogus 值长度为 28。"""
        signer = Signer()
        result = signer.sign(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            {"aweme_id": "123", "aid": "6383"},
        )
        assert len(result["X-Bogus"]) == 28

    def test_abogus_length_44(self) -> None:
        """a_bogus 值长度为 44。"""
        signer = Signer()
        result = signer.sign(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            {"aweme_id": "123", "aid": "6383"},
        )
        assert len(result["a_bogus"]) == 44

    def test_mstoken_length(self) -> None:
        """msToken 值长度约为 172。"""
        signer = Signer()
        result = signer.sign(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            {"aweme_id": "123", "aid": "6383"},
        )
        assert len(result["msToken"]) == 172

    def test_verifyfp_prefix(self) -> None:
        """verifyFp 值以 verify_ 开头。"""
        signer = Signer()
        result = signer.sign(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            {"aweme_id": "123", "aid": "6383"},
        )
        assert result["verifyFp"].startswith("verify_")

    def test_different_calls_different_mstoken(self) -> None:
        """多次调用产生不同的 msToken 和 verifyFp。"""
        signer = Signer()
        result1 = signer.sign(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            {"aweme_id": "123", "aid": "6383"},
        )
        result2 = signer.sign(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            {"aweme_id": "123", "aid": "6383"},
        )
        assert result1["msToken"] != result2["msToken"]
        assert result1["verifyFp"] != result2["verifyFp"]


class TestSignerGenerateMethods:
    """generate_ms_token() / generate_verify_fp() 测试。"""

    def test_generate_ms_token(self) -> None:
        """generate_ms_token() 正常返回。"""
        signer = Signer()
        result = signer.generate_ms_token()
        assert result
        assert isinstance(result, str)
        assert len(result) == 172

    def test_generate_verify_fp(self) -> None:
        """generate_verify_fp() 正常返回。"""
        signer = Signer()
        result = signer.generate_verify_fp()
        assert result
        assert isinstance(result, str)
        assert result.startswith("verify_")


class TestSignerUserAgent:
    """User-Agent 优先级测试。"""

    def test_default_ua(self) -> None:
        """未传入 UA 时使用默认 UA。"""
        signer = Signer()
        assert signer._user_agent == DEFAULT_USER_AGENT

    def test_custom_ua_in_constructor(self) -> None:
        """构造函数传入的 UA 覆盖默认值。"""
        custom_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0"
        signer = Signer(user_agent=custom_ua)
        assert signer._user_agent == custom_ua

    def test_sign_uses_default_ua(self) -> None:
        """sign() 未传 UA 时使用构造函数的默认 UA。"""
        signer = Signer()
        result = signer.sign(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            {"aweme_id": "123", "aid": "6383"},
        )
        assert "X-Bogus" in result

    def test_sign_explicit_ua_overrides_default(self) -> None:
        """sign() 显式传入 UA 优先于构造函数默认值。"""
        default_signer = Signer()
        custom_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0"

        result_default = default_signer.sign(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            {"aweme_id": "123", "aid": "6383"},
        )
        result_explicit = default_signer.sign(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            {"aweme_id": "123", "aid": "6383"},
            user_agent=custom_ua,
        )
        # 不同 UA 产生不同 X-Bogus
        assert result_default["X-Bogus"] != result_explicit["X-Bogus"]

    def test_class_level_default_ua_constant(self) -> None:
        """Signer.DEFAULT_USER_AGENT 类级常量与模块级常量一致。"""
        assert Signer.DEFAULT_USER_AGENT == DEFAULT_USER_AGENT


class TestSignerErrorPropagation:
    """异常传播测试。"""

    def test_empty_params_raises_sign_error(self) -> None:
        """空参数字典抛出 SignError。"""
        signer = Signer()
        with pytest.raises(SignError):
            signer.sign(
                "https://www.douyin.com/aweme/v1/web/aweme/detail/",
                {},
            )

    def test_empty_ua_raises_sign_error(self) -> None:
        """空 UA（构造函数传入空字符串）抛出 SignError。"""
        signer = Signer(user_agent="")
        with pytest.raises(SignError):
            signer.sign(
                "https://www.douyin.com/aweme/v1/web/aweme/detail/",
                {"aweme_id": "123", "aid": "6383"},
            )

    def test_sign_error_contains_algorithm(self) -> None:
        """子算法失败时 SignError 含 algorithm 标识。"""
        signer = Signer()
        with pytest.raises(SignError) as exc_info:
            signer.sign(
                "https://www.douyin.com/aweme/v1/web/aweme/detail/",
                {},
            )
        # 空参数由 ABogusSigner 检测，algorithm 应为 'abogus'
        assert exc_info.value.algorithm == "abogus"
