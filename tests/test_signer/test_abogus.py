"""A_Bogus 签名算法单元测试。

测试内容：
    - 已知输入/输出对验证
    - 确定性验证（同输入同输出）
    - 空字典/空 UA 抛出 SignError
    - 多参数组合
"""

from __future__ import annotations

import pytest

from crawlers.exceptions import SignError
from crawlers.signer.abogus import ABogusSigner

pytestmark = pytest.mark.signer


class TestABogusKnownVectors:
    """已知输入/输出对验证。"""

    @pytest.mark.parametrize("case_index", range(5))
    def test_known_vector(self, known_vectors: dict, case_index: int) -> None:
        """验证已知输入/输出对。"""
        case = known_vectors["abogus"][case_index]
        signer = ABogusSigner(timestamp_ms=case["timestamp_ms"])
        result = signer.sign(case["input"]["params"], case["input"]["user_agent"])
        assert (
            result == case["expected"]
        ), f"用例 '{case['description']}' 失败: 期望 {case['expected']}, 实际 {result}"

    def test_known_vectors_count(self, known_vectors: dict) -> None:
        """验证已知用例数量不少于 5 组。"""
        assert len(known_vectors["abogus"]) >= 5


class TestABogusDeterminism:
    """确定性验证。"""

    def test_same_input_same_output(
        self, abogus_signer: ABogusSigner, default_user_agent: str
    ) -> None:
        """同一输入多次调用返回一致结果。"""
        params = {"aweme_id": "123", "aid": "6383"}
        result1 = abogus_signer.sign(params, default_user_agent)
        result2 = abogus_signer.sign(params, default_user_agent)
        result3 = abogus_signer.sign(params, default_user_agent)
        assert result1 == result2 == result3

    def test_different_timestamp_different_output(self, default_user_agent: str) -> None:
        """不同时间戳产生不同输出。"""
        params = {"aweme_id": "123", "aid": "6383"}
        signer1 = ABogusSigner(timestamp_ms=1700000000000)
        signer2 = ABogusSigner(timestamp_ms=1700001000000)
        assert signer1.sign(params, default_user_agent) != signer2.sign(params, default_user_agent)

    def test_different_ua_different_output(self, abogus_signer: ABogusSigner) -> None:
        """不同 User-Agent 产生不同输出。"""
        params = {"aweme_id": "123", "aid": "6383"}
        ua1 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
        ua2 = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0"
        assert abogus_signer.sign(params, ua1) != abogus_signer.sign(params, ua2)

    def test_output_length_44(self, abogus_signer: ABogusSigner, default_user_agent: str) -> None:
        """输出长度为 44 字符。"""
        params = {"aweme_id": "123", "aid": "6383"}
        result = abogus_signer.sign(params, default_user_agent)
        assert len(result) == 44

    def test_output_non_empty(self, abogus_signer: ABogusSigner, default_user_agent: str) -> None:
        """输出为非空字符串。"""
        params = {"aweme_id": "123", "aid": "6383"}
        result = abogus_signer.sign(params, default_user_agent)
        assert result
        assert isinstance(result, str)


class TestABogusEmptyInput:
    """空输入边界测试。"""

    def test_empty_params_raises(
        self, abogus_signer: ABogusSigner, default_user_agent: str
    ) -> None:
        """空参数字典抛出 SignError。"""
        with pytest.raises(SignError) as exc_info:
            abogus_signer.sign({}, default_user_agent)
        assert exc_info.value.algorithm == "abogus"

    def test_empty_ua_raises(self, abogus_signer: ABogusSigner) -> None:
        """空 User-Agent 抛出 SignError。"""
        params = {"aweme_id": "123", "aid": "6383"}
        with pytest.raises(SignError) as exc_info:
            abogus_signer.sign(params, "")
        assert exc_info.value.algorithm == "abogus"

    def test_none_params_raises(self, abogus_signer: ABogusSigner, default_user_agent: str) -> None:
        """None 参数字典抛出 SignError。"""
        with pytest.raises(SignError) as exc_info:
            abogus_signer.sign(None, default_user_agent)  # type: ignore[arg-type]
        assert exc_info.value.algorithm == "abogus"

    def test_none_ua_raises(self, abogus_signer: ABogusSigner) -> None:
        """None User-Agent 抛出 SignError。"""
        params = {"aweme_id": "123", "aid": "6383"}
        with pytest.raises(SignError) as exc_info:
            abogus_signer.sign(params, None)  # type: ignore[arg-type]
        assert exc_info.value.algorithm == "abogus"


class TestABogusEdgeCases:
    """边界情况测试。"""

    def test_minimal_params(self, abogus_signer: ABogusSigner, default_user_agent: str) -> None:
        """仅含固定参数的最小请求。"""
        params = {"aid": "6383", "device_platform": "webapp"}
        result = abogus_signer.sign(params, default_user_agent)
        assert len(result) == 44

    def test_many_params(self, abogus_signer: ABogusSigner, default_user_agent: str) -> None:
        """含大量动态参数的完整请求。"""
        params = {f"param_{i}": f"value_{i}" for i in range(50)}
        params["aweme_id"] = "123"
        params["aid"] = "6383"
        result = abogus_signer.sign(params, default_user_agent)
        assert len(result) == 44

    def test_special_chars_in_params(
        self, abogus_signer: ABogusSigner, default_user_agent: str
    ) -> None:
        """参数值含特殊字符（中文、emoji）。"""
        params = {"aweme_id": "123", "aid": "6383", "keyword": "测试🎉"}
        result = abogus_signer.sign(params, default_user_agent)
        assert len(result) == 44

    def test_single_param(self, abogus_signer: ABogusSigner, default_user_agent: str) -> None:
        """仅含单个参数。"""
        params = {"aweme_id": "999"}
        result = abogus_signer.sign(params, default_user_agent)
        assert len(result) == 44
