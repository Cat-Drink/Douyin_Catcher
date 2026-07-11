"""A_Bogus 签名算法（纯 Python 自主实现）。

A_Bogus 是 X-Bogus 的升级版，引入了浏览器环境信息参与签名计算。
基于抖音 Web 前端 A_Bogus 算法的公开原理分析自主实现，不依赖任何
JS 执行环境，仅使用 Python 标准库。

算法核心流程：
    1. 由毫秒时间戳生成 4 字节随机前缀（lm_part1）
    2. 用固定种子构建 256 字节 S-Box（类似 RC4 KSA 的打乱）
    3. 将请求参数、User-Agent、浏览器环境信息组合构建 29 字节输入数据（lm_in）
    4. 用 S-Box 对 lm_in 进行 RC4-like 流密码加密，得到 29 字节密文（lm_part2）
    5. 拼接前缀 + 密文 = 33 字节混淆串
    6. 使用自定义字符表进行 Base64 变体编码，输出 44 字符 a_bogus 值

参考方向（仅参考原理，不 vendoring 代码）：
    - 公开的 A_Bogus 算法逆向分析文档
    - Evil0ctal/Douyin_TikTok_Download_API 项目的设计思路

输入/输出契约：
    - 输入：请求参数字典 params + User-Agent 字符串
    - 输出：44 字符的 a_bogus 签名字符串
    - 同一输入 + 同一时间戳产生确定输出
"""

from __future__ import annotations

import base64
import hashlib
import time
import urllib.parse

from crawlers.exceptions import SignError

# 自定义 Base64 变体字符表（64 字符，无填充符）
# 来源：抖音 Web 前端 webmssdk.js 中的常量，与 X-Bogus 的字符表不同
_ABOGUS_BASE64_TABLE: str = "Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe"

# S-Box 打乱用的固定种子（对应抖音前端 \xD3）
_SBOX_SEED: int = 211

# RC4 流密码密钥（UA 处理用，与 X-Bogus 共用设计思路）
_UA_RC4_KEY: bytes = bytes([0, 1, 14])

# lm_in 固定环境信息字节（模拟 PC Chrome 浏览器环境指纹）
# 来源：抖音前端采集的浏览器环境信息，包括屏幕分辨率、时区等
_ENV_FINGERPRINT: tuple[int, ...] = (
    0,
    4,
    0,  # 固定头部
    0,
    1,
    0,  # 固定标识
)

# lm_in 固定尾部字节
_LM_IN_TAIL: tuple[int, ...] = (14, 3)


def _build_sbox() -> list[int]:
    """构建 256 字节 S-Box。

    初始化为 [255, 254, ..., 0] 递减数组，用固定种子 211 (\xd3)
    通过类似 RC4 KSA 的方式打乱顺序。

    返回:
        256 字节 S-Box。
    """
    sbox = [255 - i for i in range(256)]
    j = 0
    for i in range(256):
        val = sbox[i]
        # j = (j * val + j + seed) % 256
        j = (j + j * val + _SBOX_SEED) % 256
        sbox[i], sbox[j] = sbox[j], sbox[i]
    return sbox


def _build_timestamp_prefix(timestamp_ms: int) -> bytes:
    """由毫秒时间戳生成 4 字节前缀。

    提取时间戳的低 16 位，通过位运算组合为 4 字节，
    每字节融合时间戳信息与固定掩码。

    参数:
        timestamp_ms: 毫秒级 Unix 时间戳。

    返回:
        4 字节前缀。
    """
    n1 = timestamp_ms & 0xFF
    n2 = (timestamp_ms >> 8) & 0xFF
    return bytes(
        [
            (n1 & 0xAA) | 0x01,
            (n1 & 0x55) | 0x02,
            (n2 & 0xAA) | 0x40,
            (n2 & 0x55) | 0x02,
        ]
    )


def _double_md5(data: bytes) -> bytes:
    """计算双重 MD5 哈希（MD5(MD5(data))）。

    参数:
        data: 原始字节序列。

    返回:
        16 字节哈希值。
    """
    return hashlib.md5(hashlib.md5(data).digest()).digest()


def _rc4_ua(user_agent: str) -> bytes:
    """对 User-Agent 进行 RC4 加密后再 base64 编码。

    使用固定密钥 [0, 1, 14] 对 UA 进行 RC4 流密码加密，
    再将密文进行 base64 编码，供后续 MD5 盐值计算使用。

    参数:
        user_agent: User-Agent 字符串。

    返回:
        base64 编码后的加密 UA 字节。
    """
    # RC4 KSA
    s_box = list(range(256))
    j = 0
    key = _UA_RC4_KEY
    key_len = len(key)
    for i in range(256):
        j = (j + s_box[i] + key[i % key_len]) % 256
        s_box[i], s_box[j] = s_box[j], s_box[i]

    # RC4 PRGA
    ua_bytes = user_agent.encode("utf-8")
    i = 0
    j = 0
    result = bytearray(len(ua_bytes))
    for k in range(len(ua_bytes)):
        i = (i + 1) % 256
        j = (j + s_box[i]) % 256
        s_box[i], s_box[j] = s_box[j], s_box[i]
        result[k] = ua_bytes[k] ^ s_box[(s_box[i] + s_box[j]) % 256]

    return base64.b64encode(bytes(result))


def _build_lm_in(params_str: str, user_agent: str, timestamp_ms: int) -> bytes:
    """构建 29 字节输入数据 lm_in。

    将请求参数串、User-Agent、浏览器环境信息组合，通过双重 MD5 盐值
    和位运算处理，生成 29 字节的中间数据。

    参数:
        params_str: 序列化后的查询参数串。
        user_agent: User-Agent 字符串。
        timestamp_ms: 毫秒级 Unix 时间戳。

    返回:
        29 字节输入数据。
    """
    # 参数串和 UA 的盐值
    salt_params = _double_md5(params_str.encode("utf-8"))
    salt_ua = hashlib.md5(_rc4_ua(user_agent)).digest()

    # 组合 29 字节 lm_in
    # 结构：环境信息 + 参数盐值 + UA 盐值 + 时间戳 + 校验位
    lm_in = bytearray()
    lm_in.extend(_ENV_FINGERPRINT)  # 字节 0-5: 环境信息 (6 字节)
    lm_in.append(salt_params[14])  # 字节 6: 参数盐值
    lm_in.append(salt_params[15])  # 字节 7
    lm_in.append(salt_ua[14])  # 字节 8: UA 盐值
    lm_in.append(salt_ua[15])  # 字节 9
    lm_in.append(salt_params[0])  # 字节 10
    lm_in.append(salt_params[1])  # 字节 11
    lm_in.append(salt_params[2])  # 字节 12
    lm_in.append(salt_params[3])  # 字节 13
    lm_in.append(salt_ua[0])  # 字节 14
    lm_in.append(salt_ua[1])  # 字节 15
    lm_in.append(salt_ua[2])  # 字节 16
    lm_in.append(salt_ua[3])  # 字节 17
    lm_in.append(salt_params[4])  # 字节 18
    lm_in.append(salt_params[5])  # 字节 19
    # 时间戳信息 (4 字节)
    lm_in.append((timestamp_ms >> 24) & 0xFF)  # 字节 20
    lm_in.append((timestamp_ms >> 16) & 0xFF)  # 字节 21
    lm_in.append((timestamp_ms >> 8) & 0xFF)  # 字节 22
    lm_in.append(timestamp_ms & 0xFF)  # 字节 23
    # 更多盐值
    lm_in.append(salt_ua[4])  # 字节 24
    lm_in.append(salt_ua[5])  # 字节 25
    lm_in.append(salt_params[6])  # 字节 26
    # 固定尾部
    lm_in.extend(_LM_IN_TAIL)  # 字节 27-28: 固定尾部 (2 字节)

    return bytes(lm_in)


def _rc4_like_encrypt(sbox: list[int], data: bytes) -> bytes:
    """使用 S-Box 对数据进行 RC4-like 流密码加密。

    与标准 RC4 的 PRGA 类似，但索引从 1 开始，且使用 S-Box 而非
    标准 RC4 的 KSA 结果。

    参数:
        sbox: 256 字节 S-Box（会被原地修改）。
        data: 待加密数据。

    返回:
        加密后的数据（长度与 data 相同）。
    """
    z = 0
    result = bytearray(len(data))
    for i in range(len(data)):
        a = (i + 1) % 256
        c = sbox[a]
        z = (z + c) % 256
        e = sbox[z]
        sbox[a], sbox[z] = sbox[z], sbox[a]
        g = (e + c) % 256
        result[i] = data[i] ^ sbox[g]
    return bytes(result)


def _abogus_base64_encode(data: bytes) -> str:
    """使用自定义字符表进行 Base64 变体编码。

    每 3 字节为一组，组合为 24 位整数，拆分为 4 个 6 位索引，查表得到 4 字符。
    33 字节 / 3 = 11 组，输出 44 字符。

    参数:
        data: 33 字节待编码数据。

    返回:
        44 字符编码结果。
    """
    result: list[str] = []
    for i in range(0, len(data), 3):
        n0 = data[i]
        n1 = data[i + 1]
        n2 = data[i + 2]
        base = (n0 << 16) | (n1 << 8) | n2
        result.append(_ABOGUS_BASE64_TABLE[(base & 0xFC0000) >> 18])
        result.append(_ABOGUS_BASE64_TABLE[(base & 0x3F000) >> 12])
        result.append(_ABOGUS_BASE64_TABLE[(base & 0xFC0) >> 6])
        result.append(_ABOGUS_BASE64_TABLE[base & 0x3F])
    return "".join(result)


def _serialize_params(params: dict) -> str:
    """将参数字典序列化为查询参数串。

    按抖音前端的参数序列化方式，使用 urlencode 编码。
    参数按字典插入顺序排列。

    参数:
        params: 请求参数字典。

    返回:
        序列化后的查询参数串。
    """
    return urllib.parse.urlencode(params)


class ABogusSigner:
    """A_Bogus 签名算法。

    输入：请求参数字典 + User-Agent。
    输出：44 字符的 a_bogus 签名字符串。

    同一输入 + 同一时间戳产生确定输出。生产环境使用当前时间戳，
    测试时可注入固定时间戳以确保确定性。
    """

    def __init__(self, timestamp_ms: int | None = None) -> None:
        """初始化 A_Bogus 签名器。

        参数:
            timestamp_ms: 固定毫秒级 Unix 时间戳，用于测试时确保确定性输出。
                None 时使用当前时间戳。
        """
        self._timestamp_ms = timestamp_ms

    def sign(self, params: dict, user_agent: str) -> str:
        """生成 a_bogus 签名。

        参数:
            params: 请求参数字典（非空）。
            user_agent: User-Agent 字符串（非空）。

        返回:
            44 字符的 a_bogus 签名字符串。

        异常:
            SignError: 输入为空或类型无效，或算法计算失败。
        """
        try:
            if not params or not isinstance(params, dict):
                raise SignError("参数字典不能为空", algorithm="abogus")
            if not user_agent or not isinstance(user_agent, str):
                raise SignError("User-Agent 不能为空", algorithm="abogus")

            # 序列化参数
            params_str = _serialize_params(params)

            # 获取时间戳（毫秒）
            ts = self._timestamp_ms if self._timestamp_ms is not None else int(time.time() * 1000)

            # 步骤 1: 生成 4 字节时间戳前缀
            prefix = _build_timestamp_prefix(ts)

            # 步骤 2: 构建 S-Box
            sbox = _build_sbox()

            # 步骤 3: 构建 29 字节输入数据
            lm_in = _build_lm_in(params_str, user_agent, ts)

            # 步骤 4: RC4-like 加密
            encrypted = _rc4_like_encrypt(sbox, lm_in)

            # 步骤 5: 拼接 4 + 29 = 33 字节
            garbled = prefix + encrypted

            # 步骤 6: Base64 变体编码 → 44 字符
            return _abogus_base64_encode(garbled)
        except SignError:
            raise
        except Exception as e:
            raise SignError(f"A_Bogus 签名计算失败: {e}", algorithm="abogus") from e
