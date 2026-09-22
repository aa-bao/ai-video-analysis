from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from src.db.models import VideoTaskRecord
from src.db.repositories import VideoTaskRepository
from src.core.identity import RequestIdentity
from src.video.config import VideoConfig
from src.video import router as video_router
from src.video.service import VideoTaskManager
from src.video.settings import VideoAgentSettings


class _ScalarRows:
    def scalars(self):
        return self

    def all(self) -> list:
        return []


class _CaptureSession:
    statement = None

    async def execute(self, statement):
        self.statement = statement
        return _ScalarRows()


def _principal(*, owner: int) -> RequestIdentity:
    """本地账号身份（独立化后已无租户 / 部门维度）。"""
    return RequestIdentity.for_local_user(owner, username="tester")


@pytest.mark.asyncio
async def test_video_repository_enforces_owner_scope() -> None:
    session = _CaptureSession()
    await VideoTaskRepository(session).list_owned(_principal(owner=17))

    compiled = session.statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    # ⚠️ 不要再断言具体占位符：MySQL 用 %s，PG 的 psycopg 风格是 %(name)s、
    # asyncpg 风格是 $1 —— 写死任何一种都会在下一次换 driver 时假失败。
    # 这里只校验「owner 过滤条件确实出现在 WHERE 子句里」，与占位符风格解耦。
    assert re.search(r"WHERE\s+rag_video_task\.owner_user_id\s*=", sql), sql
    assert 17 in compiled.params.values()
    # 独立化后已无租户维度：阶段 4 起 tenant_id / department_id 已从 schema 与 ORM 模型删除，
    # 所以这里直接校验模型映射里不存在这两列 —— 比「SQL 里没有 tenant 过滤条件」更强，
    # 因为后者在列被删掉之后会退化成永远为真的空转断言。
    assert not ({"tenant_id", "department_id"} & set(VideoTaskRecord.__table__.columns.keys()))


def _manager(tmp_path: Path) -> VideoTaskManager:
    config = VideoConfig(
        task_root=tmp_path / "tasks",
        output_root=tmp_path / "output",
        upload_dir=tmp_path / "uploads",
        library_root=tmp_path / "library",
        cookie_file=None,
        douyin_cookie_file=tmp_path / "cookies_douyin.txt",
        wx_cookie_file=tmp_path / "wx-cookies" / "cookies.json",
        python="python",
    )
    return VideoTaskManager(config, lambda: VideoAgentSettings())


@pytest.mark.asyncio
async def test_concurrent_tasks_keep_runtime_results_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path)
    first = manager.submit(
        "https://example.com/first",
        owner_user_id=1,
    )
    second = manager.submit(
        "https://example.com/second",
        owner_user_id=2,
    )
    both_started = asyncio.Event()
    started = 0

    async def resolve(*args, **kwargs) -> str:
        return "video"

    async def pipeline(task_id, source, frames, kind, settings, output, started_at, state, runtime):
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await both_started.wait()
        await asyncio.sleep(0)
        runtime.transcript = f"transcript:{task_id}"
        runtime.report = {"task_id": task_id, "cost": {}}
        runtime.summary = {"summary": source}
        runtime.keyframes = [{"path": str(output / f"{task_id}.jpg")}]

    monkeypatch.setattr(manager, "_resolve_content_type", resolve)
    monkeypatch.setattr(manager, "_pipeline_body", pipeline)

    await asyncio.gather(
        manager._run_pipeline(first["task_id"], first["source"], frames=1, kind="url"),
        manager._run_pipeline(second["task_id"], second["source"], frames=1, kind="url"),
    )

    first_state = manager.get(first["task_id"])
    second_state = manager.get(second["task_id"])
    assert first_state["transcript"] == f"transcript:{first['task_id']}"
    assert second_state["transcript"] == f"transcript:{second['task_id']}"
    assert first_state["report"]["task_id"] != second_state["report"]["task_id"]


@pytest.mark.asyncio
async def test_recovery_restarts_owned_incomplete_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path)
    manager._app = SimpleNamespace(state=SimpleNamespace(session_factory=lambda: None))
    record = SimpleNamespace(
        task_id="recover-me",
        owner_user_id=9,
        # [P6-P2-FIX3] 阶段 6 起 record_to_state 会读 owner_visitor_id（访客归属落库），
        # 这个假 record 必须一并补上，否则 record_to_state 抛 AttributeError。
        owner_visitor_id=None,
        source="https://example.com/video",
        kind="url",
        status="running",
        stage="transcribing",
        created_at=None,
        updated_at=None,
        output_dir=str(tmp_path / "output" / "recover-me"),
        error=None,
        frames_requested=3,
        transcript_source=None,
        duration_seconds=None,
        transcript=None,
        summary=None,
        report=None,
        keyframes=None,
        cost=None,
        events=None,
        qa_history=None,
        video_path=None,
        audio_path=None,
        content_type="video",
        post_text=None,
        author=None,
        hashtags=None,
        publish_time=None,
        post_images=None,
        image_captions=None,
    )

    class SessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            return None

    class FakeRepository:
        record_to_state = staticmethod(VideoTaskRepository.record_to_state)

        def __init__(self, session):
            pass

        async def list_incomplete(self):
            return [record]

    manager._app.state.session_factory = SessionContext
    started: list[tuple] = []
    monkeypatch.setattr("src.video.service.VideoTaskRepository", FakeRepository)
    monkeypatch.setattr(manager, "_save", manager.restore_cache)
    monkeypatch.setattr(manager, "start_background", lambda *args, **kwargs: started.append((args, kwargs)))

    assert await manager.recover_incomplete_tasks() == 1
    restored = manager.get("recover-me")
    assert restored["status"] == "submitted"
    assert restored["stage"] == "recovering"
    assert started[0][0][:2] == ("recover-me", "https://example.com/video")


@pytest.mark.asyncio
async def test_cancel_task_drops_pending_database_write(tmp_path: Path) -> None:
    manager = _manager(tmp_path)

    async def wait_forever() -> None:
        await asyncio.Event().wait()

    running = asyncio.create_task(wait_forever())
    persistence = asyncio.create_task(wait_forever())
    manager._running["delete-me"] = running
    manager._persist_workers["delete-me"] = persistence
    manager._pending_db_states["delete-me"] = {"task_id": "delete-me"}

    await manager.cancel_task("delete-me")

    assert running.cancelled()
    assert persistence.cancelled()
    assert "delete-me" not in manager._pending_db_states
    assert "delete-me" not in manager._persist_workers


@pytest.mark.asyncio
async def test_library_delete_waits_for_cancel_before_removing_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path)
    output_dir = manager._config.library_root / "delete-me"
    output_dir.mkdir(parents=True)
    (output_dir / "report.html").write_text("report", encoding="utf-8")
    events: list[str] = []

    async def owned_state(*args, **kwargs):
        return {"task_id": "delete-me", "output_dir": str(output_dir)}

    async def cancel_task(task_id: str) -> None:
        assert output_dir.is_dir()
        events.append("cancel")

    class SessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            return None

    class FakeRepository:
        def __init__(self, session):
            pass

        async def delete_owned(self, task_id, principal):
            assert not output_dir.exists()
            events.append("database")
            return True

    manager.cancel_task = cancel_task
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(session_factory=SessionContext))
    )
    monkeypatch.setattr(video_router, "_manager", lambda request: manager)
    monkeypatch.setattr(video_router, "_owned_task_state", owned_state)
    monkeypatch.setattr(video_router, "VideoTaskRepository", FakeRepository)

    await video_router.delete_library_task(
        "delete-me", request, _principal(owner=17)
    )

    assert events == ["cancel", "database"]


@pytest.mark.asyncio
async def test_dashscope_media_endpoint_resolves_registered_capability(
    tmp_path: Path,
) -> None:
    media = tmp_path / "chunk.mp3"
    media.write_bytes(b"audio")
    token, _ = video_router.video_asr.register_dashscope_media(
        media, "https://app.example.test/api/video/asr-media"
    )
    try:
        response = await video_router.get_dashscope_asr_media(token)
        assert Path(response.path) == media.resolve()
        assert response.headers["cache-control"] == "no-store, private"
    finally:
        video_router.video_asr.unregister_dashscope_media(token)
