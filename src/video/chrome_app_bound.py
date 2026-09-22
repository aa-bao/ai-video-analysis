"""尝试解开 Chrome 127+ 的 **App-Bound Encryption**（`v20` Cookie）。

背景：Chrome 127 起新增 `app_bound_encrypted_key`（前缀 `APPB`）。
解密链条是 **两层 DPAPI**：
  ① `APPB` 之后的密文用 **SYSTEM** 上下文 DPAPI 解 → 中间密钥
  ② 解出的中间密钥里含一段用 **当前用户** 上下文 DPAPI 保护的密钥 → 最终 AES 密钥

⚠️ 官方还要求调用方**以 Chrome 的 elevation service（COM）** 参与，
    纯本地 DPAPI 复现**未必成功**（Chrome 会校验调用者可执行文件签名/路径）。
    因此本模块是**尽力而为**：成功就返回密钥，失败返回 None，
    调用方据此降级到「手动粘贴」。**不要因为这里失败就报成用户登录失效。**

⚠️ 该实现**不写入、不修改**浏览器任何文件。
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

_APPB_PREFIX = b"APPB"
# DPAPI 的 SYSTEM 上下文
_CRYPTPROTECT_LOCAL_MACHINE = 0x4


def _dpapi_unprotect(blob: bytes, machine: bool = False) -> bytes | None:
    """DPAPI CryptUnprotectData 的 ctypes 封装（Windows）。失败返回 None。"""
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    buf = ctypes.create_string_buffer(blob, len(blob))
    blob_in = DATA_BLOB(len(blob), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    flags = _CRYPTPROTECT_LOCAL_MACHINE if machine else 0
    if not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, flags, ctypes.byref(blob_out)
    ):
        return None
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def load_app_bound_key(user_data_root: Path) -> bytes | None:
    """尽力解开 App-Bound 主密钥；成功返回 AES 密钥，失败返回 None。

    实测（本机 Chrome，2026-09-22）：**返回 None** ——
    纯 DPAPI 路径不足以复现 Chrome 的内部流程。保留实现是为了：
    ① 在 Chrome 放宽限制 / 旧版 Chrome 上仍可能成功；
    ② 把「试过什么、为什么不行」沉淀下来，避免下次重复试。
    """
    state = user_data_root / "Local State"
    if not state.is_file():
        return None
    try:
        payload = json.loads(state.read_text(encoding="utf-8"))
        enc_b64 = payload["os_crypt"]["app_bound_encrypted_key"]
        blob = base64.b64decode(enc_b64)
    except (OSError, ValueError, KeyError, TypeError):
        return None

    if not blob.startswith(_APPB_PREFIX):
        return None
    blob = blob[len(_APPB_PREFIX) :]

    # ① SYSTEM 上下文解一层
    stage1 = _dpapi_unprotect(blob, machine=True)
    if stage1 is None:
        # 某些实现在用户上下文就能解（旧版行为），再试一次
        stage1 = _dpapi_unprotect(blob, machine=False)
    if stage1 is None:
        return None

    # ② 解出的内容本身仍可能是一段 DPAPI 保护的密钥（长度 > 32）
    if len(stage1) > 32:
        stage2 = _dpapi_unprotect(stage1, machine=False)
        if stage2 is not None and len(stage2) in (16, 24, 32):
            return stage2
        # 长度刚好 32 的直接当密钥用（部分版本如此）
        if len(stage1) == 32:
            return stage1
        return None
    if len(stage1) in (16, 24, 32):
        return stage1
    return None
