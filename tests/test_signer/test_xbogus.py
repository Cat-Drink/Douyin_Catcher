"""X-Bogus 签名算法单元测试。

测试内容：
    - 已知输入/输出对验证
    - 确定性验证（同输入同输出）
    - 空输入抛出 SignError
    - 超长 URL 处理
    - 特殊字符参数处理
"""

from __future__ import annotations

import pytest

from crawlers.exceptions import SignError
from crawlers.signer.xbogus import XBogusSigner

pytestmark = pytest.mark.signer


class TestXBogusKnownVectors:
    """已知输入/输出对验证。"""

    @pytest.mark.parametrize("case_index", range(5))
    def test_known_vector(
        self, known_vectors: dict, default_user_agent: str, case_index: int
    ) -> None:
        """验证已知输入/输出对。"""
        case = known_vectors["xbogus"][case_index]
        signer = XBogusSigner(timestamp=case["timestamp"])
        result = signer.sign(case["input"]["url"], case["input"]["user_agent"])
        assert (
            result == case["expected"]
        ), f"用例 '{case['description']}' 失败: 期望 {case['expected']}, 实际 {result}"

    def test_known_vectors_count(self, known_vectors: dict) -> None:
        """验证已知用例数量不少于 5 组。"""
        assert len(known_vectors["xbogus"]) >= 5


class TestXBogusDeterminism:
    """确定性验证。"""

    def test_same_input_same_output(
        self, xbogus_signer: XBogusSigner, default_user_agent: str
    ) -> None:
        """同一输入多次调用返回一致结果。"""
        url = "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123&aid=6383"
        result1 = xbogus_signer.sign(url, default_user_agent)
        result2 = xbogus_signer.sign(url, default_user_agent)
        result3 = xbogus_signer.sign(url, default_user_agent)
        assert result1 == result2 == result3

    def test_different_timestamp_different_output(self, default_user_agent: str) -> None:
        """不同时间戳产生不同输出。"""
        url = "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123&aid=6383"
        signer1 = XBogusSigner(timestamp=1700000000)
        signer2 = XBogusSigner(timestamp=1700001000)
        assert signer1.sign(url, default_user_agent) != signer2.sign(url, default_user_agent)

    def test_different_ua_different_output(self, xbogus_signer: XBogusSigner) -> None:
        """不同 User-Agent 产生不同输出。"""
        url = "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123&aid=6383"
        ua1 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
        ua2 = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0"
        assert xbogus_signer.sign(url, ua1) != xbogus_signer.sign(url, ua2)

    def test_output_length_28(self, xbogus_signer: XBogusSigner, default_user_agent: str) -> None:
        """输出长度为 28 字符。"""
        url = "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123&aid=6383"
        result = xbogus_signer.sign(url, default_user_agent)
        assert len(result) == 28

    def test_output_non_empty(self, xbogus_signer: XBogusSigner, default_user_agent: str) -> None:
        """输出为非空字符串。"""
        url = "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123&aid=6383"
        result = xbogus_signer.sign(url, default_user_agent)
        assert result
        assert isinstance(result, str)


class TestXBogusEmptyInput:
    """空输入边界测试。"""

    def test_empty_url_raises(self, xbogus_signer: XBogusSigner, default_user_agent: str) -> None:
        """空 URL 抛出 SignError。"""
        with pytest.raises(SignError) as exc_info:
            xbogus_signer.sign("", default_user_agent)
        assert exc_info.value.algorithm == "xbogus"

    def test_empty_ua_raises(self, xbogus_signer: XBogusSigner) -> None:
        """空 User-Agent 抛出 SignError。"""
        url = "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123&aid=6383"
        with pytest.raises(SignError) as exc_info:
            xbogus_signer.sign(url, "")
        assert exc_info.value.algorithm == "xbogus"

    def test_none_url_raises(self, xbogus_signer: XBogusSigner, default_user_agent: str) -> None:
        """None URL 抛出 SignError。"""
        with pytest.raises(SignError) as exc_info:
            xbogus_signer.sign(None, default_user_agent)  # type: ignore[arg-type]
        assert exc_info.value.algorithm == "xbogus"

    def test_none_ua_raises(self, xbogus_signer: XBogusSigner) -> None:
        """None User-Agent 抛出 SignError。"""
        url = "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123&aid=6383"
        with pytest.raises(SignError) as exc_info:
            xbogus_signer.sign(url, None)  # type: ignore[arg-type]
        assert exc_info.value.algorithm == "xbogus"


class TestXBogusEdgeCases:
    """边界情况测试。"""

    def test_long_url(self, xbogus_signer: XBogusSigner, default_user_agent: str) -> None:
        """超长 URL（> 2000 字符）应正常处理。"""
        # 构造超长 URL
        long_param = "x" * 2000
        url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123&aid=6383&data={long_param}"
        result = xbogus_signer.sign(url, default_user_agent)
        assert len(result) == 28

    def test_special_chars_chinese(
        self, xbogus_signer: XBogusSigner, default_user_agent: str
    ) -> None:
        """中文参数正确处理。"""
        url = "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123&aid=6383&keyword=%E6%B5%8B%E8%AF%95"
        result = xbogus_signer.sign(url, default_user_agent)
        assert len(result) == 28

    def test_special_chars_emoji(
        self, xbogus_signer: XBogusSigner, default_user_agent: str
    ) -> None:
        """emoji 参数正确处理（URL 编码形式）。"""
        url = "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123&aid=6383&emoji=%F0%9F%98%80"
        result = xbogus_signer.sign(url, default_user_agent)
        assert len(result) == 28

    def test_query_only_no_domain(
        self, xbogus_signer: XBogusSigner, default_user_agent: str
    ) -> None:
        """仅查询参数串（无域名和 ?）正常处理。"""
        result = xbogus_signer.sign("aweme_id=123&aid=6383", default_user_agent)
        assert len(result) == 28

    def test_minimal_params(self, xbogus_signer: XBogusSigner, default_user_agent: str) -> None:
        """仅含固定参数的最小请求。"""
        url = "https://www.douyin.com/aweme/v1/web/aweme/detail/?aid=6383&device_platform=webapp"
        result = xbogus_signer.sign(url, default_user_agent)
        assert len(result) == 28

    def test_many_dynamic_params(
        self, xbogus_signer: XBogusSigner, default_user_agent: str
    ) -> None:
        """含大量动态参数的完整请求。"""
        params = "&".join(f"param_{i}=value_{i}" for i in range(50))
        url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123&aid=6383&{params}"
        result = xbogus_signer.sign(url, default_user_agent)
        assert len(result) == 28
