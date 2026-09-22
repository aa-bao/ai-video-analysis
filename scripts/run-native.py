# -*- coding: utf-8 -*-
"""P2 原生形态启动器：注入 .env -> 起 uvicorn（8000+ 端口按需）。

P2 的 create_app 不自动加载 .env（config.yaml 用 ${ENV} 占位符），
故必须由启动器把 .env 写进 os.environ 再 create_app。
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"


def load_env(path: pathlib.Path) -> int:
    n = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()
        n += 1
    return n


if __name__ == "__main__":
    n = load_env(ENV_FILE)
    os.environ.setdefault("APP_DATA_ROOT", str(ROOT / "data"))
    os.environ.setdefault("APP_SECRET_ROOT", str(ROOT / "secrets"))
    sys.path.insert(0, str(ROOT))

    if "--probe" in sys.argv:
        # ⚠️ 别用 isinstance(r, APIRoute) 数路由：fastapi >=0.13x 用惰性的
        # `_IncludedRouter` 包装（include_router 时不在 app.routes 里展开），
        # 那种数法会恒返回 0/2 条，误判成「路由没注册」。正解读 app.openapi()。
        from src.api.app import create_app

        app = create_app()
        paths = sorted(app.openapi().get("paths", {}))
        print(f"env keys={n} | openapi paths={len(paths)}")
        for p in paths:
            print("  ", p)
        raise SystemExit(0)

    import uvicorn

    port = int(os.environ.get("P2_PORT", "8011"))
    uvicorn.run(
        "src.api.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=port,
        log_level="info",
    )
