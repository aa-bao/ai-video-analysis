"""P2 测试夹具。

`tests/test_video/` 以纯单元测试为主；阶段 6 起新增访客配额集成测试，需要真实
PostgreSQL + pgvector。

[P6-P2-FIX4] 集成测试的库由**测试自己现拉一个临时容器**提供（与 P1
`rag-service/tests/conftest.py` 同一手法），而不是复用部署用的 `xxzw-postgres`。
理由：既有约定是「测试自带临时 PG 容器，不依赖 compose 里的 postgres 服务」——
复用部署容器会让 `pytest` 在没有起部署栈的机器 / CI 上直接失败，
也会把测试与运行环境耦合在一起。
"""
from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

SCHEMA_SQL = Path(__file__).resolve().parents[1] / "schema.sql"

# pgvector 镜像：优先本机已缓存的加速域名，拉不到再回退官方镜像（与 P1 一致）。
PG_TEST_IMAGE = "docker.m.daocloud.io/pgvector/pgvector:pg17"
PG_TEST_IMAGE_FALLBACK = "pgvector/pgvector:pg17"

# 当前测试 PG 容器名（带随机后缀避免并发冲突）。
_PG_CONTAINER_NAME: str | None = None


def _pg_test_image() -> str:
    env_image = os.environ.get("PG_TEST_IMAGE")
    if env_image:
        return env_image
    probe = subprocess.run(
        ["docker", "image", "inspect", PG_TEST_IMAGE],
        capture_output=True,
        text=True,
    )
    return PG_TEST_IMAGE if probe.returncode == 0 else PG_TEST_IMAGE_FALLBACK


def _apply_schema_sql(database_url: str) -> None:
    """把 schema.sql 灌入指定库（通过容器内 psql，管道执行）。"""
    match = re.fullmatch(
        r"postgresql\+asyncpg://([^:]+):([^@]+)@127\.0\.0\.1:(\d+)/(\w+)",
        database_url,
    )
    assert match, f"unexpected pg_url: {database_url}"
    user, password, _port, dbname = match.groups()
    result = subprocess.run(
        [
            "docker", "exec", "-i", _PG_CONTAINER_NAME,
            "psql", "-h", "127.0.0.1", "-U", user, "-d", dbname,
            "-v", "ON_ERROR_STOP=1",
        ],
        input=SCHEMA_SQL.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        env={**os.environ, "PGPASSWORD": password},
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """一次性 pgvector 容器，指向**空库** `video`（postgresql+asyncpg://）。"""
    name = f"video-pg-test-{uuid.uuid4().hex[:10]}"
    password = "test-root-password"
    image = _pg_test_image()
    run = subprocess.run(
        [
            "docker", "run", "--detach", "--rm", "--name", name,
            "--env", f"POSTGRES_PASSWORD={password}",
            "--env", "POSTGRES_DB=video",
            "--publish", "127.0.0.1::5432",
            image,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert run.stdout.strip()

    global _PG_CONTAINER_NAME
    _PG_CONTAINER_NAME = name
    try:
        port_output = subprocess.run(
            ["docker", "port", name, "5432/tcp"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        port = int(port_output.rsplit(":", 1)[1])

        # 就绪探测必须走 TCP：官方镜像初始化期会先起一个只监听 socket 的临时
        # server，socket 探测会误判「已就绪」。
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            probe = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                capture_output=True,
                text=True,
            )
            if probe.returncode == 0:
                break
            time.sleep(1)
        else:
            logs = subprocess.run(
                ["docker", "logs", name], capture_output=True, text=True
            ).stdout
            pytest.fail(f"PostgreSQL did not become ready://n{logs}")

        yield f"postgresql+asyncpg://postgres:{password}@127.0.0.1:{port}/video"
    finally:
        _PG_CONTAINER_NAME = None
        subprocess.run(
            ["docker", "rm", "--force", name], check=False, capture_output=True
        )


@pytest.fixture(scope="session")
def migrated_pg_url(pg_url: str) -> str:
    """指向**已灌入 schema.sql** 的库（复用 pg_url 的容器与库）。"""
    _apply_schema_sql(pg_url)
    return pg_url
