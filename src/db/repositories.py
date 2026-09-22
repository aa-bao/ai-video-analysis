from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import VideoSetting, VideoTaskRecord
from src.db.scope import scope_condition
from src.core.identity import RequestIdentity
from src.shared.errors import AppError


def _parse_dt(value: object) -> datetime | None:
    """把任务状态里的时间字段归一化成 **naive UTC** datetime。

    [P6-P2-FIX] 本函数原先被 `VideoTaskRepository._row_values` 调用却**从未定义**
    （全仓 0 处 def）→ 每次落库都抛 ``NameError: name '_parse_dt' is not defined``，
    ``persist_to_db(strict=True)`` 因此让 ``POST /tasks`` 恒返回 503。

    口径：同一函数里 ``now = datetime.now(UTC).replace(tzinfo=None)`` 是 naive UTC，
    所以这里也统一成 naive UTC，避免同一列混进带时区/不带时区两种值。
    入参可能是 ``record_to_state`` 产出的 ISO 字符串（含 ``Z`` 或 ``+08:00``），
    也可能是内存态里的 ``datetime``；无法解析时返回 ``None``（由调用方回落 ``now``）。
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw_text = value.strip()
        if raw_text.endswith(("Z", "z")):
            raw_text = raw_text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw_text)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


class VideoSettingRepository:
    """视频解析 agent 设置持久化：单行（id=1）的读与 upsert。"""

    SETTING_ID = 1

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> VideoSetting | None:
        return await self._session.scalar(
            select(VideoSetting).where(VideoSetting.id == self.SETTING_ID)
        )

    async def upsert(self, values: dict[str, str | int]) -> None:
        """已有行则更新，否则插入 id=1。"""
        setting = await self.get()
        if setting is None:
            setting = VideoSetting(
                id=self.SETTING_ID,
                asr_provider=str(values["asr_provider"]),
                asr_model=str(values["asr_model"]),
                asr_api_key=str(values["asr_api_key"]),
                asr_app_id=str(values.get("asr_app_id") or ""),
                asr_access_token=str(values.get("asr_access_token") or ""),
                chat_base_url=str(values["chat_base_url"]),
                chat_model=str(values["chat_model"]),
                chat_api_key=str(values["chat_api_key"]),
                qa_model=str(values.get("qa_model") or ""),
                qa_base_url=str(values.get("qa_base_url") or ""),
                qa_api_key=str(values.get("qa_api_key") or ""),
                frames=int(values["frames"]),
            )
            self._session.add(setting)
        else:
            setting.asr_provider = str(values["asr_provider"])
            setting.asr_model = str(values["asr_model"])
            setting.asr_api_key = str(values["asr_api_key"])
            setting.asr_app_id = str(values.get("asr_app_id") or "")
            setting.asr_access_token = str(values.get("asr_access_token") or "")
            setting.chat_base_url = str(values["chat_base_url"])
            setting.chat_model = str(values["chat_model"])
            setting.chat_api_key = str(values["chat_api_key"])
            setting.qa_model = str(values.get("qa_model") or "")
            setting.qa_base_url = str(values.get("qa_base_url") or "")
            setting.qa_api_key = str(values.get("qa_api_key") or "")
            setting.frames = int(values["frames"])
        await self._session.commit()

class VideoTaskRepository:
    """视频解析任务结果持久化：以 task_id 为业务唯一键的 upsert。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _row_values(self, state: dict[str, Any]) -> dict[str, Any]:
        report = state.get("report") if isinstance(state.get("report"), dict) else {}
        duration = report.get("duration_seconds") if report else None
        if not isinstance(duration, (int, float)):
            duration = state.get("duration_seconds")
        if not isinstance(duration, (int, float)):
            duration = None

        created = _parse_dt(state.get("created_at"))
        updated = _parse_dt(state.get("updated_at"))
        now = datetime.now(UTC).replace(tzinfo=None)
        return {
            "task_id": str(state.get("task_id") or ""),
            "owner_user_id": state.get("owner_user_id"),
            "owner_visitor_id": state.get("owner_visitor_id"),
            "source": str(state.get("source") or ""),
            "kind": str(state.get("kind") or "url"),
            "status": str(state.get("status") or "submitted"),
            "stage": state.get("stage") or None,
            "created_at": created or now,
            "updated_at": updated or now,
            "output_dir": state.get("output_dir") or None,
            "error": state.get("error") or None,
            "frames_requested": state.get("frames_requested"),
            "transcript_source": state.get("transcript_source") or None,
            "duration_seconds": float(duration) if duration is not None else None,
            "transcript": state.get("transcript") or None,
            "summary": state.get("summary") if isinstance(state.get("summary"), dict) else None,
            "report": report or None,
            "keyframes": state.get("keyframes") if isinstance(state.get("keyframes"), list) else None,
            "cost": state.get("cost") if isinstance(state.get("cost"), dict) else None,
            "events": state.get("events") if isinstance(state.get("events"), list) else None,
            "qa_history": state.get("qa_history") if isinstance(state.get("qa_history"), list) else None,
            "video_path": state.get("video_path") or None,
            "audio_path": state.get("audio_path") or None,
            "content_type": str(state.get("content_type") or "video"),
            "post_text": state.get("post_text") or None,
            "author": state.get("author") or None,
            "hashtags": state.get("hashtags") if isinstance(state.get("hashtags"), list) else None,
            "publish_time": state.get("publish_time") or None,
            "post_images": state.get("post_images") if isinstance(state.get("post_images"), list) else None,
            "image_captions": state.get("image_captions") if isinstance(state.get("image_captions"), dict) else None,
        }

    async def upsert_state(self, state: dict[str, Any]) -> None:
        """以 ``task_id`` 为唯一键的**原子** upsert（阶段 6 修正）。

        [P6-P2-FIX2] 原实现是「先 SELECT，再 INSERT / 逐字段 setattr UPDATE」。
        同一 task 存在两条**并发**落库路径：

        1. ``VideoTaskManager.submit()`` → ``_save()`` → ``_schedule_persist()``
           → ``_flush_persisted_state()`` → ``persist_to_db(state)``（非 strict）；
        2. ``src/video/router.py::submit_task`` → ``persist_to_db(state, strict=True)``。

        两条路径会各自 SELECT 到 None、各自 INSERT，后到者撞
        ``uq_video_task_task_id`` → 上抛 → ``POST /tasks`` 间歇性 503
        （已完成受理的任务被判为「数据库不可用」）。

        改为 PG 原生 ``INSERT ... ON CONFLICT (task_id) DO UPDATE``：单语句、原子、幂等，
        与函数名 ``upsert_state`` 的语义一致。
        ``owner_user_id`` 与 ``task_id`` 不参与 UPDATE（一旦落库不再被后续状态改写）。
        """
        values = self._row_values(state)
        if not values["task_id"]:
            return
        update_columns = {
            key: value
            for key, value in values.items()
            if key not in {"task_id", "owner_user_id"}
        }
        stmt = pg_insert(VideoTaskRecord).values(**values)
        if update_columns:
            stmt = stmt.on_conflict_do_update(
                index_elements=[VideoTaskRecord.task_id],
                set_=update_columns,
            )
        else:
            stmt = stmt.on_conflict_do_nothing(
                index_elements=[VideoTaskRecord.task_id]
            )
        await self._session.execute(stmt)
        await self._session.commit()

    @staticmethod
    def record_to_state(record: VideoTaskRecord) -> dict[str, Any]:
        return {
            "task_id": record.task_id,
            "owner_user_id": record.owner_user_id,
            "owner_visitor_id": record.owner_visitor_id,
            "source": record.source,
            "kind": record.kind,
            "status": record.status,
            "stage": record.stage,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            "output_dir": record.output_dir,
            "error": record.error,
            "frames_requested": record.frames_requested,
            "transcript_source": record.transcript_source,
            "duration_seconds": record.duration_seconds,
            "transcript": record.transcript,
            "summary": record.summary,
            "report": record.report,
            "keyframes": record.keyframes,
            "cost": record.cost,
            "events": record.events,
            "qa_history": record.qa_history,
            "video_path": record.video_path,
            "audio_path": record.audio_path,
            "content_type": record.content_type or "video",
            "post_text": record.post_text,
            "author": record.author,
            "hashtags": record.hashtags,
            "publish_time": record.publish_time,
            "post_images": record.post_images,
            "image_captions": record.image_captions,
            "cache_manifest": None,
            "pid": None,
        }

    async def get(self, task_id: str) -> VideoTaskRecord | None:
        return await self._session.scalar(
            select(VideoTaskRecord).where(VideoTaskRecord.task_id == task_id)
        )

    async def get_owned(
        self, task_id: str, principal: RequestIdentity
    ) -> VideoTaskRecord | None:
        return await self._session.scalar(
            select(VideoTaskRecord).where(
                VideoTaskRecord.task_id == task_id,
                VideoTaskRecord.owner_user_id == principal.user_id,
                scope_condition(VideoTaskRecord, principal),
            )
        )

    async def list(self, limit: int = 100) -> list[VideoTaskRecord]:
        result = await self._session.execute(
            select(VideoTaskRecord)
            .order_by(VideoTaskRecord.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_owned(
        self, principal: RequestIdentity, limit: int = 100
    ) -> list[VideoTaskRecord]:
        result = await self._session.execute(
            select(VideoTaskRecord)
            .where(
                VideoTaskRecord.owner_user_id == principal.user_id,
                scope_condition(VideoTaskRecord, principal),
            )
            .order_by(VideoTaskRecord.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_incomplete(self, limit: int = 100) -> list[VideoTaskRecord]:
        result = await self._session.execute(
            select(VideoTaskRecord)
            .where(VideoTaskRecord.status.in_(("submitted", "running")))
            .order_by(VideoTaskRecord.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete(self, task_id: str) -> None:
        record = await self.get(task_id)
        if record is not None:
            await self._session.delete(record)
            await self._session.commit()

    async def delete_owned(self, task_id: str, principal: RequestIdentity) -> bool:
        record = await self.get_owned(task_id, principal)
        if record is None:
            return False
        await self._session.delete(record)
        await self._session.commit()
        return True
