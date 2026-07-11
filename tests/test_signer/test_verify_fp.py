"""verify_fp / s_v_web_id 生成单元测试。

测试内容：
    - verify_ 前缀校验
    - 格式校验
    - 随机性
"""

from __future__ import annotations

import pytest

from crawlers.signer.verify_fp import VerifyFpGenerator

pytestmark = pytest.mark.signer


class TestVerifyFpPrefix:
    """前缀校验。"""

    def test_starts_with_verify_prefix(self, verify_fp_generator: VerifyFpGenerator) -> None:
        """输出以 verify_ 开头。"""
        result = verify_fp_generator.generate()
        assert result.startswith("verify_")

    def test_s_v_web_id_starts_with_verify_prefix(
        self, verify_fp_generator: VerifyFpGenerator
    ) -> None:
        """s_v_web_id 以 verify_ 开头。"""
        result = verify_fp_generator.generate_s_v_web_id()
        assert result.startswith("verify_")


class TestVerifyFpFormat:
    """格式校验。"""

    def test_non_empty(self, verify_fp_generator: VerifyFpGenerator) -> None:
        """输出为非空字符串。"""
        result = verify_fp_generator.generate()
        assert result
        assert isinstance(result, str)

    def test_length(self, verify_fp_generator: VerifyFpGenerator) -> None:
        """输出长度符合预期（约 52 字符）。"""
        result = verify_fp_generator.generate()
        # verify_ (7) + 8 lowercase + _ (1) + 8+4+4+4+12 = 7+8+1+32 = 48
        assert len(result) >= 48

    def test_format_structure(self, verify_fp_generator: VerifyFpGenerator) -> None:
        """格式结构：verify_<8位小写字母>_<UUID风格8-4-4-4-12>。"""
        result = verify_fp_generator.generate()
        # 去掉 verify_ 前缀
        body = result[len("verify_") :]
        parts = body.split("_")
        # 第一段 8 位小写字母 + 5 段 UUID 风格
        assert len(parts) == 6
        assert len(parts[0]) == 8
        assert parts[0].isalpha()
        assert parts[0].islower()
        assert len(parts[1]) == 8
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 4
        assert len(parts[5]) == 12

    def test_s_v_web_id_same_format(self, verify_fp_generator: VerifyFpGenerator) -> None:
        """s_v_web_id 与 verify_fp 格式一致。"""
        result = verify_fp_generator.generate_s_v_web_id()
        body = result[len("verify_") :]
        parts = body.split("_")
        assert len(parts) == 6


class TestVerifyFpRandomness:
    """随机性测试。"""

    def test_consecutive_calls_different(self, verify_fp_generator: VerifyFpGenerator) -> None:
        """连续两次调用产生不同值。"""
        result1 = verify_fp_generator.generate()
        result2 = verify_fp_generator.generate()
        assert result1 != result2

    def test_100_calls_no_duplicate(self, verify_fp_generator: VerifyFpGenerator) -> None:
        """连续调用 100 次无重复值。"""
        results = {verify_fp_generator.generate() for _ in range(100)}
        assert len(results) == 100

    def test_generate_and_s_v_web_id_different(
        self, verify_fp_generator: VerifyFpGenerator
    ) -> None:
        """generate() 和 generate_s_v_web_id() 产生不同值。"""
        result1 = verify_fp_generator.generate()
        result2 = verify_fp_generator.generate_s_v_web_id()
        assert result1 != result2
