"""P2 · AI 视频解析 Agent 的应用装配（阶段 5a 从 P1 组合根裁出）。

与 P1 `src/api/app.py` 的差异，逐条有据：

1. **不装配 RAG 侧任何组件** —— `IngestWorker` / `PgVectorRetrieval` /
   `Settings.rag|upload|llm|lexical` 全部不在本项目范围（闭包实测无引用）。
2. **不装配 `RuntimeModelRelay`** —— P1 用它做「系统模型中转」的运行时热更新；
   P2 的模型配置由 `config.yaml` 静态提供。P2 真正可变的配置是
   `VideoAgentSettings`（ASR / Chat / 帧数），由 `VideoAgentSettingsService`
   负责 DB 恢复与保存，与系统中转无关。
3. **`app.state.settings_shell` 与 `app.state.model_relay_client` 仍然提供** ——
   `video/summary.py:make_chat_client()` 在「VideoAgentSettings 未配置 Chat」时
   会回退到系统中转通道（`summary.py` 的 `return (ChatClient(app.state.settings_shell, ...))`
   分支），这两个 state 就是那条回退分支的依赖。删掉它们会让「只用 ASR、
   不配 Chat」的部署在生成摘要时 AttributeError。
"""
from __future__ import annotations

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.router_auth import router as auth_router
from src.api.router_users import router as users_router
from src.core.config import app_env
from src.models.client import ModelRelayClient
from src.shared.config import Settings
from src.shared.errors import AppError
from src.video.config import VideoConfig
from src.video.router import router as video_router
from src.video.service import VideoTaskManager
from src.video.settings import VideoAgentSettings, VideoAgentSettingsService

# src/api/app.py -> src/api -> src -> <项目根>
_PROJECT_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]


def _make_settings_shell(settings: Settings):
    """可变壳：让 ChatClient 通过 `settings.model_relay.*` 读取配置。

    与 P1 同构（P1 的壳包着 RuntimeModelRelay.client_view()，这里直接包静态配置）。
    """
    return type("_SettingsShell", (), {"model_relay": settings.model_relay})()


def create_app(
    settings: Settings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> FastAPI:
    app = FastAPI(title="AI Video Insight Agent")

    if settings is None:
        settings = Settings.load(_PROJECT_ROOT / "config.yaml", environment=app_env())
    app.state.settings = settings

    # 视频解析 agent（流水线内建；视频状态以文件系统为实时源，PG 作存档与统计）
    video_config = VideoConfig.load(environment=app_env())
    app.state.video_settings = VideoAgentSettings.from_env()
    app.state.video_manager = VideoTaskManager(
        video_config,
        get_settings=lambda: app.state.video_settings,
        app=app,
    )

    if session_factory is None:
        from src.db.session import create_engine as db_create_engine

        engine = db_create_engine(
            settings.database.url.get_secret_value(),
            pool_size=settings.database.pool_size,
            pool_recycle=settings.database.pool_recycle_seconds,
        )
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.session_factory = session_factory

    app.state.video_settings_service = VideoAgentSettingsService(
        app.state.video_settings, session_factory
    )

    # trust_env=False：外部模型服务直连为受控策略，不继承环境代理（与 P1 口径一致）
    model_client = httpx.AsyncClient(
        timeout=settings.model_relay.timeout_seconds, trust_env=False
    )
    app.state.settings_shell = _make_settings_shell(settings)
    app.state.model_relay_client = ModelRelayClient(app.state.settings_shell, model_client)

    @app.on_event("startup")
    async def _startup_restore() -> None:
        # 从 DB 恢复视频 agent 已保存的设置（ASR / Chat / 帧数），
        # 并恢复上次进程中断时未完成的任务。
        await app.state.video_settings_service.restore()
        await app.state.video_manager.recover_incomplete_tasks()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        app.state.video_manager.shutdown()
        await app.state.model_relay_client._client.aclose()

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(video_router)

    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": {"code": exc.code, "message": exc.message}},
        )

    @app.get("/api/health/live")
    async def live() -> dict[str, object]:
        return {"success": True, "data": {"status": "live"}}

    @app.get("/api/health/ready")
    async def ready() -> JSONResponse:
        try:
            async with app.state.session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(
                status_code=503, content={"success": False, "data": {"status": "unready"}}
            )
        return JSONResponse(
            status_code=200, content={"success": True, "data": {"status": "ready"}}
        )

    # SPA 静态兜底：优先本地 web/dist（开发），退回镜像内 static/
    static_dir = _PROJECT_ROOT / "web" / "dist"
    if not static_dir.exists():
        static_dir = _PROJECT_ROOT / "static"

    if static_dir.exists() and (static_dir / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="spa")

    return app
