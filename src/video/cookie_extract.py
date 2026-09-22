"""从本机浏览器**自动导出**抖音 Cookie（Netscape 格式）。

为什么要这个模块：原先只能「手动从浏览器里一条条抠 Cookie 再粘贴」，
抖音登录态过期后这个流程极其折磨人。这里直接读本地 Chromium 系浏览器的
Cookie 库（Chrome / Edge / Brave），按域名过滤出抖音相关项并转成
Netscape 格式 —— 用户在浏览器里登录一次，点一下按钮即可。

⚠️ 三条硬约束（都是实测踩出来的，改动前先读）：

1. **Chrome ≥ 80 的 Cookie 值是 AES-GCM 加密的**，密钥放在
   `Local State` 的 `os_crypt.encrypted_key`（base64，前缀 `DPAPI` 三字节），
   需先用 Windows DPAPI 解出主密钥，再用它解每条 Cookie 的
   `v10`/`v11` 前缀密文（nonce 12 字节 + 密文 + tag 16 字节）。
   ⚠️ **本机曾出现过 DPAPI 解密失败**（见用户级记忆），因此本模块
   对解密失败**逐条降级**（跳过该条并计入 `failed`），绝不整体抛错 ——
   否则一条坏数据会让整次导出失败。
2. **必须先把 Cookie 库整个复制到临时目录再读**。Chrome 运行时对
   `Cookies` 文件持有独占锁，直接打开会 `database is locked`。
   复制时 **`-wal` / `-shm` 必须一起带**，否则会读到旧快照
   （WAL 里未 checkpoint 的数据就读不到 → 少 Cookie）。
3. **只读、不改浏览器任何文件**。全程 `mode=ro` 打开副本。

依赖：`cryptography`（AES-GCM）。缺了不要崩，返回结构化错误让上层提示。
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

# 抖音相关域名（与 cookies.py 的校验口径保持一致）
DOUYIN_DOMAINS = ("douyin.com", "iesdouyin.com")

# Chromium 系浏览器的用户数据根目录（Windows）。
_BROWSER_ROOTS: dict[str, str] = {
    "chrome": r"Google\Chrome\User Data",
    "edge": r"Microsoft\Edge\User Data",
    "brave": r"BraveSoftware\Brave-Browser\User Data",
}

# Chrome 的 Cookie 加密前缀
# ⚠️ `v20` 是 Chrome 127+ 的 **App-Bound Encryption**（密钥在 `Local State` 的
# `app_bound_encrypted_key`，前缀 `APPB`，由 Chrome 的 elevation service 保护）。
# 它**不能**用 `encrypted_key` 直接 AES-GCM 解开 —— 需另走 COM 调用，本模块
# **不支持**，遇到时如实报告条数（见 `unsupported_v20`），不要假装成功。
_V10_PREFIXES = (b"v10", b"v11")
_V20_PREFIX = b"v20"


class CookieExtractError(RuntimeError):
    """导出失败（浏览器未安装 / 库不存在 / 依赖缺失等）。"""


def _user_data_root(db: Path) -> Path:
    """由 Cookie 库路径反推 **User Data 根**。

    ⚠️ `Local State` 位于 **User Data 根**，不在 `Default/` 里。
    实测：`.../User Data/Default/Network/Cookies` → 根是 `.../User Data`。
    Chrome 的 `Default`、Edge 的 `Profile 1` 都只往上一层。
    """
    p = db
    # Cookies → Network → <Profile> → User Data
    if p.parent.name == "Network":
        return p.parent.parent.parent
    return p.parent.parent


def _candidate_cookie_db_paths() -> list[tuple[str, Path]]:
    """列出本机存在的浏览器 Cookie 库（按浏览器名 + 配置文件）。"""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return []
    out: list[tuple[str, Path]] = []
    for browser, suffix in _BROWSER_ROOTS.items():
        root = Path(local) / suffix
        if not root.is_dir():
            continue
        # Default + Profile N（多用户配置文件）
        for profile in sorted(root.glob("Default")) + sorted(root.glob("Profile *")):
            db = profile / "Network" / "Cookies"
            if not db.is_file():
                # 老版本 Chrome 放在 profile 根下
                db = profile / "Cookies"
            if db.is_file():
                out.append((f"{browser}:{profile.name}", db))
    return out


def _load_master_key(user_data_root: Path) -> bytes | None:
    """从 `Local State` 取 AES 主密钥（DPAPI 解包）。

    返回 None 表示拿不到（旧版明文存储、或 Local State 缺失）。
    """
    state = user_data_root / "Local State"
    if not state.is_file():
        return None
    try:
        payload = json.loads(state.read_text(encoding="utf-8"))
        enc_b64 = payload["os_crypt"]["encrypted_key"]
    except (OSError, ValueError, KeyError):
        return None

    try:
        blob = base64.b64decode(enc_b64)
    except (ValueError, TypeError):
        return None
    # 前缀 "DPAPI" 是标记，不是密文的一部分
    if blob.startswith(b"DPAPI"):
        blob = blob[5:]

    try:
        import win32crypt  # type: ignore
    except ImportError:
        # 没装 pywin32 时退回 ctypes 直调 DPAPI
        return _dpapi_unprotect_ctypes(blob)

    try:
        _desc, key = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
        return key
    except Exception:  # noqa: BLE001 — DPAPI 失败原因多样，一律降级
        return None


def _dpapi_unprotect_ctypes(blob: bytes) -> bytes | None:
    """用 ctypes 直调 CryptUnprotectData（避免硬依赖 pywin32）。"""
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:  # 非 Windows
        return None

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    buf = ctypes.create_string_buffer(blob, len(blob))
    blob_in = DATA_BLOB(len(blob), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        return None
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _load_app_bound_key_safe(user_data_root: Path) -> bytes | None:
    """取 App-Bound 主密钥（`v20` 用）。任何异常都降级为 None，不阻断导出。"""
    try:
        from src.video.chrome_app_bound import load_app_bound_key
    except ImportError:
        return None
    try:
        return load_app_bound_key(user_data_root)
    except Exception:  # noqa: BLE001
        return None


def _decrypt_value(
    value: bytes, master_key: bytes | None, abe_key: bytes | None = None
) -> tuple[str | None, str]:
    """解出一条 Cookie 的值。

    返回 `(value, status)`：
    - `value` 非 None = 成功；空串是合法值
    - `status` ∈ `{"ok", "v20", "no_key", "failed"}`
      `v20` 表示 App-Bound 加密解不开，需单独计数以便如实告知用户，
      **不要混进 "failed"**，否则用户会以为是自己登录态失效。
    """
    if not value:
        return "", "ok"
    if value.startswith(_V20_PREFIX):
        # v20：nonce 12 + 密文 + tag 16，同样 AES-GCM，但密钥来自 App-Bound
        if abe_key is None:
            return None, "v20"
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            return None, "v20"
        try:
            nonce = value[3:15]
            plain = AESGCM(abe_key).decrypt(nonce, value[15:], None)
            return plain.decode("utf-8"), "ok"
        except Exception:  # noqa: BLE001
            return None, "v20"
    # 未加密（很旧的版本）
    if not value.startswith(_V10_PREFIXES):
        try:
            return value.decode("utf-8"), "ok"
        except UnicodeDecodeError:
            return None, "failed"

    if master_key is None:
        return None, "no_key"

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        return None, "no_key"

    try:
        nonce = value[3:15]
        ciphertext = value[15:]
        plain = AESGCM(master_key).decrypt(nonce, ciphertext, None)
        return plain.decode("utf-8"), "ok"
    except Exception:  # noqa: BLE001 — 单条失败不阻断整体
        return None, "failed"




def _copy_db_with_wal(src: Path) -> Path:
    """把 Cookie 库（含 `-wal` / `-shm`）复制到临时目录后返回副本路径。

    ⚠️ 不带 `-wal` 会读到 checkpoint 之前的旧快照 → 少 Cookie。
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="xxzw-cookies-"))
    dst = tmpdir / "Cookies"
    shutil.copy2(src, dst)
    for suffix in ("-wal", "-shm"):
        side = src.with_name(src.name + suffix)
        if side.is_file():
            shutil.copy2(side, dst.with_name(dst.name + suffix))
    return dst


def _query_douyin_rows(db: Path) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = conn.execute(
            "SELECT host_key, name, encrypted_value, path, expires_utc, "
            "is_secure, is_httponly FROM cookies"
        )
        return list(cur.fetchall())
    finally:
        conn.close()


def _to_netscape(
    rows: list[tuple[Any, ...]], master_key: bytes | None, abe_key: bytes | None = None
) -> tuple[str, dict[str, Any]]:
    """把库里的抖音行转成 Netscape 文本，并返回统计。"""
    lines: list[str] = ["# Netscape HTTP Cookie File"]
    kept = 0
    skipped = 0
    failed = 0
    v20 = 0
    domains: set[str] = set()

    for host_key, name, enc_value, path, expires_utc, secure, httponly in rows:
        host = str(host_key or "")
        host_l = host.lower().lstrip(".")
        if not any(d in host_l for d in DOUYIN_DOMAINS):
            continue
        try:
            value, status = _decrypt_value(bytes(enc_value or b""), master_key, abe_key)
        except Exception:  # noqa: BLE001
            value, status = None, "failed"
        if status == "v20":
            v20 += 1
            continue
        if value is None:
            failed += 1
            continue
        if not value:
            skipped += 1
            continue


        # Chrome 的 expires_utc 是「1601-01-01 起的微秒」；Netscape 要 Unix 秒
        try:
            exp_us = int(expires_utc or 0)
        except (TypeError, ValueError):
            exp_us = 0
        if exp_us > 0:
            unix_s = max(0, (exp_us // 1_000_000) - 11_644_473_600)
        else:
            unix_s = 0

        domain = host if host.startswith(".") else host
        lines.append(
            "\t".join(
                [
                    f"#HttpOnly_{domain}" if httponly else domain,
                    "TRUE" if host.startswith(".") else "FALSE",
                    str(path or "/"),
                    "TRUE" if secure else "FALSE",
                    str(unix_s),
                    str(name),
                    value,
                ]
            )
        )
        kept += 1
        domains.add(host_l)

    text = "\n".join(lines) + "\n"
    return text, {
        "cookie_count": kept,
        "skipped_empty": skipped,
        "failed_decrypt": failed,
        "unsupported_v20": v20,
        "domains": sorted(domains),
    }



def extract_douyin_cookie(browser: str | None = None) -> dict[str, Any]:
    """从本机浏览器导出抖音 Cookie（Netscape 文本）。

    `browser` 形如 `"chrome"` / `"edge"` 或 `"chrome:Default"`；None = 自动挑
    第一个有抖音 Cookie 的库。

    返回：`{"content": <Netscape 文本>, "source": ..., "cookie_count": ..., ...}`
    失败抛 `CookieExtractError`（带可直接展示给用户的中文原因）。
    """
    candidates = _candidate_cookie_db_paths()
    if not candidates:
        raise CookieExtractError(
            "未在本机找到 Chrome / Edge / Brave 的 Cookie 库。"
            "请确认浏览器已安装并至少登录过抖音。"
        )

    if browser:
        want = browser.strip().lower()
        candidates = [
            (n, p) for (n, p) in candidates if n.lower() == want or n.lower().startswith(want + ":")
        ] or candidates

    best: dict[str, Any] | None = None
    tried: list[str] = []
    v20_seen: set[str] = set()
    abe_available: set[str] = set()

    for name, db in candidates:
        try:
            root = _user_data_root(db)
            # `v10`/`v11` 用 os_crypt.encrypted_key；`v20` 需 App-Bound 密钥。
            master_key = _load_master_key(root)
            abe_key = _load_app_bound_key_safe(root)
            if abe_key is not None:
                abe_available.add(name)
            copy = _copy_db_with_wal(db)
            try:
                rows = _query_douyin_rows(copy)
            finally:
                shutil.rmtree(copy.parent, ignore_errors=True)
            text, stats = _to_netscape(rows, master_key, abe_key)
        except (OSError, sqlite3.Error) as exc:
            tried.append(f"{name}（读取失败：{exc}）")
            continue


        if stats["cookie_count"] == 0:
            if stats["unsupported_v20"]:
                v20_seen.add(name)
                tried.append(
                    f"{name}（{stats['unsupported_v20']} 条抖音 Cookie 是 "
                    f"v20 / App-Bound 加密，本工具暂不支持）"
                )
            else:
                tried.append(f"{name}（0 条抖音 Cookie，可能未登录）")
            continue

        result: dict[str, Any] = {
            "content": text,
            "source": name,
            "db_path": str(db),
            **stats,
        }
        # 取抖音 Cookie 最多的那个库
        if best is None or result["cookie_count"] > best["cookie_count"]:
            best = result

    if best is None:
        if v20_seen:
            raise CookieExtractError(
                "本机浏览器的抖音 Cookie 全部是 v20（App-Bound 加密），"
                "当前工具无法解密。请改用「手动粘贴 Cookie」方式更新。"
                f"（涉及：{'；'.join(sorted(v20_seen))}）"
            )
        raise CookieExtractError(
            "找到浏览器 Cookie 库，但没有可用的抖音 Cookie。"
            + ("；".join(tried) if tried else "")
            + "请先在浏览器里登录抖音，再重试。"
        )
    return best

