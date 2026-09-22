"""回归保护：抖音 Cookie 自动导出 + 「开始解析」按钮去掉旋转动效。

本文件锁死两类**真实踩过的坑**：

1. `cookie_extract` 的两处结构性错误 —— 只靠"看代码"很容易再犯：
   - `Local State` 在 **User Data 根**，不在 `Default/` 里（放错 → 主密钥恒 None）
   - Chrome 127+ 的 `v20`（App-Bound）解不开时，**不能把它算作
     "登录失效"**，必须单独计数（`unsupported_v20`）如实报告
2. 复制 Cookie 库时必须**带上 `-wal`**，否则读到 checkpoint 前的旧快照。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.video import cookie_extract as ce


# ── A. 路径推导：Local State 在 User Data 根 ──


def test_user_data_root_from_chrome_layout() -> None:
    """Chrome: Cookies → Network → Default → User Data（往上一层）。"""
    db = Path("C:/X/User Data/Default/Network/Cookies")
    assert ce._user_data_root(db) == Path("C:/X/User Data")


def test_user_data_root_from_profile_layout() -> None:
    """Edge 的 `Profile 1` 同样只往上一层。"""
    db = Path("C:/X/User Data/Profile 1/Network/Cookies")
    assert ce._user_data_root(db) == Path("C:/X/User Data")


def test_user_data_root_legacy_layout() -> None:
    """老版 Chrome 把 Cookies 直接放 profile 根下。"""
    db = Path("C:/X/User Data/Default/Cookies")
    assert ce._user_data_root(db) == Path("C:/X/User Data")


def test_local_state_must_be_at_user_data_root(tmp_path: Path) -> None:
    """回归：Local State 放 Default/ 里应**取不到** key（说明根算对了）。"""
    root = tmp_path / "User Data"
    (root / "Default" / "Network").mkdir(parents=True)
    # 故意错放：Local State 在 Default/ 而不是 User Data/
    (root / "Default" / "Local State").write_text('{"os_crypt":{}}', encoding="utf-8")
    assert ce._load_master_key(root) is None


# ── B. 解密状态：v20 必须与 failed 分开 ──


def test_v20_reported_not_as_failure() -> None:
    """v20 无法解 → status='v20'，**不是** 'failed'。"""
    value, status = ce._decrypt_value(b"v20" + b"\x00" * 40, master_key=None)
    assert value is None
    assert status == "v20"


def test_v10_without_key_reports_no_key() -> None:
    value, status = ce._decrypt_value(b"v10" + b"\x00" * 40, master_key=None)
    assert value is None
    assert status == "no_key"


def test_plaintext_value_passes_through() -> None:
    value, status = ce._decrypt_value(b"plain-value", master_key=None)
    assert value == "plain-value"
    assert status == "ok"


def test_empty_value_is_ok() -> None:
    value, status = ce._decrypt_value(b"", master_key=None)
    assert value == ""
    assert status == "ok"


# ── C. Netscape 转换 ──


def _row(host: str, name: str, value: bytes, *, httponly: int = 0, secure: int = 1):
    """Chrome cookies 表的 7 列。"""
    return (host, name, value, "/", 13_400_000_000_000_000, secure, httponly)


def test_netscape_only_keeps_douyin_domains() -> None:
    rows = [
        _row(".douyin.com", "sessionid", b"abc"),
        _row(".google.com", "NID", b"xyz"),
        _row("www.iesdouyin.com", "sid_tt", b"def"),
    ]
    text, stats = ce._to_netscape(rows, master_key=None)
    assert stats["cookie_count"] == 2
    assert "douyin.com" in text
    assert "google.com" not in text
    # domains 记录去前导点后的**原始 host**（保留 www. 子域）
    assert sorted(stats["domains"]) == ["douyin.com", "www.iesdouyin.com"]


def test_netscape_counts_v20_separately() -> None:
    """回归：v20 计入 unsupported_v20，且**不进入正文**。"""
    rows = [
        _row(".douyin.com", "ok_one", b"plain"),
        _row(".douyin.com", "v20_one", b"v20" + b"\x00" * 40),
    ]
    text, stats = ce._to_netscape(rows, master_key=None)
    assert stats["cookie_count"] == 1
    assert stats["unsupported_v20"] == 1
    assert stats["failed_decrypt"] == 0
    assert "v20_one" not in text


def test_netscape_httponly_prefix_and_header() -> None:
    rows = [_row(".douyin.com", "sid", b"v", httponly=1)]
    text, _ = ce._to_netscape(rows, master_key=None)
    assert text.splitlines()[0] == "# Netscape HTTP Cookie File"
    assert "#HttpOnly_.douyin.com" in text


def test_netscape_expiry_conversion() -> None:
    """Chrome 的 expires_utc（1601 微秒）要转成 Unix 秒。"""
    rows = [_row(".douyin.com", "sid", b"v")]
    text, _ = ce._to_netscape(rows, master_key=None)
    line = [ln for ln in text.splitlines() if "sid" in ln][0]
    unix_s = int(line.split("\t")[4])
    # 13400000000000000 微秒 ≈ 2025 年，必须在合理区间
    assert 1_700_000_000 < unix_s < 1_900_000_000


# ── D. WAL 复制：必须带上 -wal / -shm ──


def test_copy_db_carries_wal_sidecars(tmp_path: Path) -> None:
    src = tmp_path / "Cookies"
    src.write_bytes(b"db")
    (tmp_path / "Cookies-wal").write_bytes(b"wal")
    (tmp_path / "Cookies-shm").write_bytes(b"shm")

    copy = ce._copy_db_with_wal(src)
    try:
        assert copy.read_bytes() == b"db"
        assert copy.with_name("Cookies-wal").read_bytes() == b"wal"
        assert copy.with_name("Cookies-shm").read_bytes() == b"shm"
    finally:
        import shutil

        shutil.rmtree(copy.parent, ignore_errors=True)


def test_copy_db_without_sidecars_still_works(tmp_path: Path) -> None:
    src = tmp_path / "Cookies"
    src.write_bytes(b"db")
    copy = ce._copy_db_with_wal(src)
    try:
        assert copy.read_bytes() == b"db"
        assert not copy.with_name("Cookies-wal").exists()
    finally:
        import shutil

        shutil.rmtree(copy.parent, ignore_errors=True)


# ── E. 端到端：v20-only 场景必须给出**可操作**的错误 ──


def test_extract_raises_actionable_error_when_only_v20(tmp_path: Path, monkeypatch) -> None:
    """只有 v20 时，错误信息必须点明「改手动粘贴」，不是笼统失败。"""
    root = tmp_path / "User Data"
    profile = root / "Default" / "Network"
    profile.mkdir(parents=True)

    db = profile / "Cookies"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE cookies (host_key TEXT, name TEXT, encrypted_value BLOB, "
        "path TEXT, expires_utc INTEGER, is_secure INTEGER, is_httponly INTEGER)"
    )
    conn.execute(
        "INSERT INTO cookies VALUES ('.douyin.com','sid',?,'/',0,1,0)",
        (b"v20" + b"\x00" * 40,),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(ce, "_candidate_cookie_db_paths", lambda: [("chrome:Default", db)])
    monkeypatch.setattr(ce, "_load_master_key", lambda _root: None)
    monkeypatch.setattr(ce, "_load_app_bound_key_safe", lambda _root: None)

    with pytest.raises(ce.CookieExtractError) as ei:
        ce.extract_douyin_cookie()
    msg = str(ei.value)
    assert "v20" in msg
    assert "手动粘贴" in msg


def test_extract_no_browsers_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ce, "_candidate_cookie_db_paths", lambda: [])
    with pytest.raises(ce.CookieExtractError) as ei:
        ce.extract_douyin_cookie()
    assert "未在本机找到" in str(ei.value)


def test_extract_returns_best_when_plaintext_present(tmp_path: Path, monkeypatch) -> None:
    """有明文 Cookie 时应成功返回，并挑抖音条数最多的库。"""
    root = tmp_path / "User Data"
    profile = root / "Default" / "Network"
    profile.mkdir(parents=True)
    db = profile / "Cookies"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE cookies (host_key TEXT, name TEXT, encrypted_value BLOB, "
        "path TEXT, expires_utc INTEGER, is_secure INTEGER, is_httponly INTEGER)"
    )
    for i in range(3):
        conn.execute(
            "INSERT INTO cookies VALUES ('.douyin.com',?,?,'/',0,1,0)",
            (f"c{i}", b"plain"),
        )
    conn.commit()
    conn.close()

    monkeypatch.setattr(ce, "_candidate_cookie_db_paths", lambda: [("chrome:Default", db)])
    monkeypatch.setattr(ce, "_load_master_key", lambda _root: None)
    monkeypatch.setattr(ce, "_load_app_bound_key_safe", lambda _root: None)

    r = ce.extract_douyin_cookie()
    assert r["cookie_count"] == 3
    assert r["source"] == "chrome:Default"
    assert r["unsupported_v20"] == 0
