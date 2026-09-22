"""ASR 转写：双渠道（volcengine / dashscope），按 settings.asr_provider 切换。

- volcengine：火山引擎语音技术 · 大模型录音文件极速识别（flash）。
  接口 POST https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash
  - 一次请求即返回识别结果（无需 submit/query 轮询）。
  - 音频 base64 直传（建议 ≤20MB；我们的分片为 16k mp3，约 1-2MB）。
  - 响应 utterances 自带 begin/end 毫秒时间戳，直接产出 [MM:SS] 句子行。
  凭证（settings.asr_headers）：
  - 新版控制台：X-Api-Key（单一 key）
  - 旧版控制台：X-Api-App-Key + X-Api-Access-Key
  - 固定：X-Api-Resource-Id=volc.bigasr.auc_turbo、X-Api-Request-Id=uuid、X-Api-Sequence=-1

- dashscope：阿里云百炼 · qwen-audio-3.0-asr-flash-filetrans / qwen3-asr-flash-filetrans
  录音文件识别（异步）。
  接口 POST https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription
  - 提交 task（X-DashScope-Async: enable）→ 轮询 GET /api/v1/tasks/{id} → 取转写文本。
  - input 字段按模型族二选一：qwen3-asr-flash-filetrans 用 file_url（单值），
    qwen-audio-3.0-asr-flash-filetrans / fun-asr-* 用 file_urls（数组）。
  - 音频必须为公网可访问 URL：通过应用现有 HTTPS /api 入口提供随机、限时
    capability URL，转写完成后立即注销；不开放额外静态文件监听端口。
  - 响应 sentences 自带 begin_time/end_time（秒），直接产出 [MM:SS] 句子行。

新增 provider 只需在 asr.py 增加分支 + settings 提供对应凭证/端点字段，
火山与百炼互不影响，后续可随时切换。
"""
from __future__ import annotations

import base64
import os
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

from src.core.config import PRODUCTION_ENVIRONMENTS, app_env
from src.video.settings import DASHSCOPE_ASR_MODEL_DEFAULT
from src.video.settings import DASHSCOPE_ASR_PROVIDERS as DASHSCOPE_PROVIDERS
from src.video.transcript import format_time, format_utterance_entries

# ── 渠道常量 ──
# 火山：端点可用 VOLC_ASR_ENDPOINT 覆盖（网关代理 / 测试桩场景）
VOLC_RECOGNIZE_URL = os.environ.get(
    "VOLC_ASR_ENDPOINT",
    "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash",
)
# 百炼：提交/轮询端点可分别覆盖（网关代理 / 测试桩场景）
DASHSCOPE_SUBMIT_URL = os.environ.get(
    "DASHSCOPE_ASR_ENDPOINT",
    "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription",
)
DASHSCOPE_TASK_URL = os.environ.get(
    "DASHSCOPE_ASR_TASK_URL",
    "https://dashscope.aliyuncs.com/api/v1/tasks",
)
# 百炼：文件上传凭证端点（getPolicy），用于「本地文件直传 OSS」通路。
DASHSCOPE_UPLOAD_POLICY_URL = os.environ.get(
    "DASHSCOPE_ASR_UPLOAD_POLICY_URL",
    "https://dashscope.aliyuncs.com/api/v1/uploads",
)
# 使用 oss:// 临时 URL 时必须带的请求头，否则服务端无法解析该协议。
OSS_RESOLVE_HEADER = {"X-DashScope-OssResourceResolve": "enable"}

class AsrError(RuntimeError):
    """ASR 调用失败（含凭证/权限/服务错误）。"""


def _public_dir() -> Path:
    """百炼需要公网 URL 拉取音频；分片先复制到这里对外提供，用完即删。"""
    root = Path(os.environ.get("QUICK_WATCH_TASK_ROOT", "")).expanduser()
    if root.is_absolute():
        return root.parent / "asr_public"
    return Path.cwd() / "data" / "asr_public"


# ── 百炼：经应用入口提供的临时 capability URL ──

_MEDIA_LOCK = threading.Lock()
_MEDIA_TOKENS: dict[str, tuple[Path, float]] = {}


def register_dashscope_media(
    path: Path, public_base_url: str, *, ttl_seconds: float = 900.0
) -> tuple[str, str]:
    base_url = public_base_url.strip().rstrip("/")
    parsed = urlparse(base_url)
    environment = app_env()
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise AsrError("DASHSCOPE_ASR_PUBLIC_BASE_URL must be an HTTP(S) URL")
    if environment in PRODUCTION_ENVIRONMENTS and parsed.scheme != "https":
        raise AsrError("DASHSCOPE_ASR_PUBLIC_BASE_URL must use HTTPS in production environments")
    if not path.is_file():
        raise AsrError("DashScope media file is unavailable")
    token = uuid.uuid4().hex + uuid.uuid4().hex
    with _MEDIA_LOCK:
        _MEDIA_TOKENS[token] = (path.resolve(), time.monotonic() + max(30.0, ttl_seconds))
    return token, f"{base_url}/{token}"


def resolve_dashscope_media(token: str) -> Path | None:
    now = time.monotonic()
    with _MEDIA_LOCK:
        for expired, (_, deadline) in list(_MEDIA_TOKENS.items()):
            if deadline <= now:
                _MEDIA_TOKENS.pop(expired, None)
        item = _MEDIA_TOKENS.get(token)
    if item is None or not item[0].is_file():
        return None
    return item[0]


def unregister_dashscope_media(token: str | None) -> None:
    if not token:
        return
    with _MEDIA_LOCK:
        _MEDIA_TOKENS.pop(token, None)


def _volc_user_id() -> str:
    return f"rag-video-{uuid.uuid4().hex}"


def _redact_vendor_error(value: object, settings) -> str:
    message = str(value or "ASR request failed")
    for secret in (
        getattr(settings, "asr_api_key", ""),
        getattr(settings, "asr_app_id", ""),
        getattr(settings, "asr_access_token", ""),
    ):
        if secret:
            message = message.replace(str(secret), "[REDACTED]")
    message = re.sub(
        r"(?i)(authorization|x-api-key|x-api-access-key)(\s*[:=]\s*)\S+",
        r"\1\2[REDACTED]",
        message,
    )
    return message[:500]


# ── 百炼：filetrans 异步提交 / 轮询 / 取文本 ──

# 百炼「非实时语音识别」两类模型对 input 字段的要求不同：
# - qwen3-asr-flash-filetrans                       → input.file_url  （单值字符串）
# - qwen-audio-3.x-asr-flash-filetrans / fun-asr-*  → input.file_urls（数组）
# 两者都传会被判参数非法，故按模型名前缀二选一。
_MULTI_URL_MODEL_PREFIXES = ("qwen-audio-3.", "fun-asr")


def _dashscope_input_payload(model: str, file_url: str) -> dict[str, object]:
    """按模型族构造 input 字段（file_url 单值 / file_urls 数组）。"""
    name = (model or "").strip().lower()
    if name.startswith(_MULTI_URL_MODEL_PREFIXES):
        return {"file_urls": [file_url]}
    return {"file_url": file_url}


def _dashscope_get_upload_policy(api_key: str, model: str) -> dict:
    """取文件上传凭证（getPolicy）。返回 data 字段（含 upload_host / policy 等）。"""
    with httpx.Client(timeout=30, trust_env=False) as client:
        resp = client.get(
            DASHSCOPE_UPLOAD_POLICY_URL,
            params={"action": "getPolicy", "model": model},
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
    body = resp.json() if resp.content else {}
    if resp.status_code != 200:
        raise AsrError(
            f"百炼上传凭证获取失败 HTTP {resp.status_code}: "
            f"{body.get('message') or resp.text[:200]}"
        )
    data = body.get("data") or {}
    if not data.get("upload_host") or not data.get("policy"):
        raise AsrError(f"百炼上传凭证字段不完整: {str(body)[:200]}")
    return data


def _dashscope_upload_to_oss(
    policy: dict, path: Path, api_key: str, *, timeout: float = 120.0
) -> str:
    """按凭证把本地文件直传阿里云 OSS，返回 oss:// 前缀的临时 URL。

    表单字段名与大小写必须与官方一致；官方约束「一次只传一个文件」。
    """
    filename = path.name
    object_key = f"{str(policy.get('upload_dir') or '').strip('/')}/{filename}"
    # 官方要求 file 必须是最后一个表单域；其余字段无顺序要求。
    # 用 files= 列出顺序即可满足（httpx 按传入顺序编码）。
    form = [
        ("OSSAccessKeyId", (None, str(policy.get("oss_access_key_id") or ""))),
        ("policy", (None, str(policy.get("policy") or ""))),
        ("Signature", (None, str(policy.get("signature") or ""))),
        ("key", (None, object_key)),
        ("x-oss-object-acl", (None, str(policy.get("x_oss_object_acl") or "private"))),
        (
            "x-oss-forbid-overwrite",
            (None, str(policy.get("x_oss_forbid_overwrite") or "true")),
        ),
        ("success_action_status", (None, "200")),
        ("file", (filename, path.read_bytes(), "application/octet-stream")),
    ]
    host = str(policy.get("upload_host") or "").rstrip("/")
    with httpx.Client(timeout=timeout, trust_env=False) as client:
        resp = client.post(host, files=form)
    # OSS 回调成功即 200/204；非 2xx 视为失败（响应体是 OSS 的 XML 错误）
    if resp.status_code not in (200, 204):
        raise AsrError(
            f"百炼 OSS 上传失败 HTTP {resp.status_code}: {resp.text[:200]}"
        )
    return f"oss://{object_key}"


def _dashscope_upload_via_policy(path: Path, model: str, api_key: str) -> str:
    """本地文件 → OSS 临时 URL（两步：取凭证 → 直传）。"""
    policy = _dashscope_get_upload_policy(api_key, model)
    return _dashscope_upload_to_oss(policy, path, api_key)


def _dashscope_submit(
    model: str, file_url: str, api_key: str, endpoint: str, *, oss: bool = False
) -> str:
    payload = {
        "model": model,
        "input": _dashscope_input_payload(model, file_url),
        "parameters": {"channel_id": [0], "enable_itn": False},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    # oss:// 临时 URL 必须带解析头，否则服务端无法读取该协议的文件
    if oss:
        headers.update(OSS_RESOLVE_HEADER)
    with httpx.Client(timeout=30, trust_env=False) as client:
        resp = client.post(endpoint, json=payload, headers=headers)
    body = resp.json() if resp.content else {}
    if resp.status_code != 200:
        raise AsrError(
            f"百炼提交失败 HTTP {resp.status_code}: "
            f"{body.get('message') or resp.text[:200]}"
        )
    task_id = (body.get("output") or {}).get("task_id")
    if not task_id:
        raise AsrError(f"百炼提交未返回 task_id: {str(body)[:200]}")
    return task_id

def _extract_sentences(data) -> list[dict]:
    """从转写结果 JSON 提取句子列表（兼容多种层级结构）。

    ⚠️ 3.x 的真实结构是 `transcripts[].sentences[]`：
        {"transcripts":[{"channel_id":0,"text":"...","sentences":[{begin_time,end_time,text}]}]}
    旧实现按 `("sentences","utterances","results")` 顺序递归，会**先命中 `results`** ——
    而 `output.results[].results` 是空数组（那一层只是子任务占位），于是提前返回 []，
    导致 3.x 模型**永远识别出 0 句**（提交/轮询都成功、文本却是空的，极难察觉）。
    现在改为：优先找 sentences / utterances（真正的句子数组），只在都没有时才退回 results，
    并且**递归到底**把嵌套里的句子都收上来。
    """
    found: list[dict] = []
    seen_lists: set[int] = set()

    def walk(node, depth=0):
        if depth > 10:
            return
        if isinstance(node, dict):
            for k in ("sentences", "utterances"):
                v = node.get(k)
                if isinstance(v, list) and id(v) not in seen_lists:
                    seen_lists.add(id(v))
                    for item in v:
                        if isinstance(item, dict) and str(item.get("text") or "").strip():
                            found.append(item)
            for k, v in node.items():
                if k in ("sentences", "utterances"):
                    continue  # 已处理
                walk(v, depth + 1)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)

    walk(data)
    if found:
        return found

    # 兜底：极少数渠道把句子放在 results 里（火山风格 / 兼容层）
    def first_list(node, depth=0):
        if depth > 8:
            return None
        if isinstance(node, list):
            return node
        if isinstance(node, dict):
            for k in ("results", "sentences", "utterances"):
                v = node.get(k)
                if isinstance(v, list):
                    return v
                r = first_list(v, depth + 1)
                if r is not None:
                    return r
            for v in node.values():
                r = first_list(v, depth + 1)
                if r is not None:
                    return r
        return None

    return [
        s
        for s in (first_list(data) or [])
        if isinstance(s, dict) and str(s.get("text") or "").strip()
    ]

def _find_url(node, depth=0) -> str | None:
    """递归查找转写结果 URL（兼容 transcription_url / ur_l 两种键）。"""
    if depth > 8:
        return None
    if isinstance(node, dict):
        for k in ("transcription_url", "ur_l"):
            v = node.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
        for v in node.values():
            r = _find_url(v, depth + 1)
            if r:
                return r
    return None


def _dashscope_poll_and_fetch(task_id: str, api_key: str, deadline: float) -> list[dict]:
    headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client(timeout=30, trust_env=False) as client:
        while True:
            if time.perf_counter() >= deadline - 1:
                raise AsrError("ASR 转写超时（百炼轮询）")
            resp = client.get(f"{DASHSCOPE_TASK_URL}/{task_id}", headers=headers)
            body = resp.json() if resp.content else {}
            if resp.status_code != 200:
                raise AsrError(
                    f"百炼查询失败 HTTP {resp.status_code}: "
                    f"{body.get('message') or resp.text[:200]}"
                )
            out = body.get("output") or body
            status = out.get("task_status")
            if status in ("SUCCEEDED", "SUCCESS_WITH_NO_VALID_FRAGMENT"):
                if status == "SUCCESS_WITH_NO_VALID_FRAGMENT":
                    # 空音频/无有效语音：非凭证错误，视为成功（无内容），与火山静音处理一致
                    return []
                url = _find_url(body)
                if not url:
                    raise AsrError("百炼转写成功但响应缺少转录结果 URL")
                tr = client.get(url, headers=headers, timeout=60)
                data = tr.json() if tr.content else {}
                return _extract_sentences(data)
            if status in ("FAILED", "CANCELED"):
                raise AsrError(
                    f"百炼转写失败: {out.get('message') or out.get('code') or status}"
                )
            time.sleep(2.0)

def _sentence_times(s: dict) -> tuple[float, float]:
    """提取句子时间，返回 (起, 止) 秒。

    ⚠️ 单位按**键名**判定，不靠数值大小猜：
    - 百炼 3.x 用 `begin_time` / `end_time`，单位**毫秒**
      （实测 `{"begin_time":120,"end_time":4000}` = 0.12s→4.0s）
    - 旧兼容路径可能给 `start_time` / `end_time` 的秒值
    旧实现用「值 > 1000 就当毫秒」猜单位：短音频首句起点如 120ms 会被当成 **120 秒**
    （显示 `[02:00]` 而非 `[00:00]`），且 end 取 begin 兜底后整句时长为 0 —— 静默错。
    """
    # ⚠️ 判据必须落在**起始键**上：`begin_time` 存在才是百炼 3.x。
    # 若写成 `"begin_time" in s or "end_time" in s`，旧格式 `{"start_time":1.5,"end_time":3.0}`
    # 会因**含 end_time** 误入毫秒分支 → 秒值再除 1000，静默错。
    if "begin_time" in s:
        # 百炼 3.x：毫秒
        raw_b = s.get("begin_time", 0)
        raw_e = s.get("end_time", raw_b)
        divisor = 1000.0
    else:
        raw_b = s.get("start_time", 0)
        raw_e = s.get("end_time", raw_b)
        divisor = 1.0

    def to_sec(v: object) -> float:
        try:
            return float(v) / divisor
        except (TypeError, ValueError):
            return 0.0

    b = to_sec(raw_b)
    e = to_sec(raw_e)
    return b, max(e, b)

def _dashscope_sentences_to_entries(
    sentences: list[dict], chunk_start: float
) -> list[tuple[float, str]]:
    """百炼 sentences → (绝对秒, 文本) 条目（时间戳为秒）。"""
    entries: list[tuple[float, str]] = []
    for s in sentences:
        text = str(s.get("text") or "").strip()
        if not text:
            continue
        begin, _end = _sentence_times(s)
        entries.append((round(chunk_start + begin, 3), text))
    return entries


def _transcribe_chunk_dashscope(
    index: int,
    start: float,
    chunk_path: Path,
    settings,
    request_timeout: float = 120.0,
    retries: int = 1,
) -> dict[str, object]:
    """百炼 filetrans：异步提交 + 轮询。

    音频送入方式二选一（由 settings.asr_upload_mode 决定）：
    - `oss`（默认）：本地文件经 getPolicy 直传阿里云 OSS → `oss://` 临时 URL，
      提交时带 `X-DashScope-OssResourceResolve: enable`。**不要求本机可被公网访问**，
      本地开发即可跑通。
    - `public-url`：把分片经内置静态服务暴露成公网 capability URL（需
      `DASHSCOPE_ASR_PUBLIC_BASE_URL`），适合已部署到服务器、有公网域名时。
    """
    started = time.perf_counter()
    request_deadline = started + max(1.0, request_timeout)
    error = "unknown error"
    api_calls = 0
    public_file: Path | None = None
    media_token: str | None = None
    upload_mode = (getattr(settings, "asr_upload_mode", "") or "oss").strip().lower()
    use_oss = upload_mode != "public-url"
    for attempt in range(retries + 1):
        if time.perf_counter() >= request_deadline - 1:
            error = "ASR request budget exhausted"
            break
        try:
            api_key = (settings.asr_api_key or "").strip()
            if not api_key:
                raise AsrError(
                    "ASR 凭证未配置：请在 agent 设置页填写百炼 API Key，"
                    "或配置 .env 的 DASHSCOPE_ASR_API_KEY"
                )
            model = (settings.asr_model or DASHSCOPE_ASR_MODEL_DEFAULT).strip()
            endpoint = (settings.asr_endpoint or "").strip() or DASHSCOPE_SUBMIT_URL

            if use_oss:
                file_url = _dashscope_upload_via_policy(chunk_path, model, api_key)
            else:
                public_base_url = (settings.asr_public_base_url or "").strip()
                if not public_base_url:
                    raise AsrError(
                        "未配置 DashScope 媒体入口：请设置 "
                        "DASHSCOPE_ASR_PUBLIC_BASE_URL，或改用 ASR_UPLOAD_MODE=oss"
                    )
                public_dir = _public_dir()
                public_dir.mkdir(parents=True, exist_ok=True)
                public_file = (
                    public_dir / f"{uuid.uuid4().hex}{chunk_path.suffix or '.mp3'}"
                )
                public_file.write_bytes(chunk_path.read_bytes())
                media_token, file_url = register_dashscope_media(
                    public_file, public_base_url, ttl_seconds=request_timeout + 60
                )

            api_calls += 1
            task_id = _dashscope_submit(
                model, file_url, api_key, endpoint, oss=use_oss
            )
            sentences = _dashscope_poll_and_fetch(task_id, api_key, request_deadline)

            entries = _dashscope_sentences_to_entries(sentences, start)
            all_text = "\n".join(f"[{format_time(sec)}] {txt}" for sec, txt in entries)
            return {
                "index": index,
                "start": start,
                "text": all_text,
                "raw_utterances": sentences,
                "language": None,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "attempts": api_calls,
                "error": None,
            }
        except AsrError as exc:
            error = _redact_vendor_error(exc, settings)
            # 凭证/权限类错误不重试
            if any(k in error for k in ("401", "403", "未配置", "没有权限", "InvalidParameter")):
                break
            if attempt < retries:
                time.sleep(min(0.5 * (attempt + 1), max(0, request_deadline - time.perf_counter())))
        except Exception as exc:  # noqa: BLE001 — 网络/超时等，统一进入重试
            error = _redact_vendor_error(exc, settings)
            if attempt < retries:
                time.sleep(min(0.5 * (attempt + 1), max(0, request_deadline - time.perf_counter())))
        finally:
            unregister_dashscope_media(media_token)
            media_token = None
            if public_file is not None:
                try:
                    public_file.unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass
    return {
        "index": index,
        "start": start,
        "text": "",
        "language": None,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "attempts": api_calls,
        "error": error,
    }


# ── 火山：flash 极速识别（原实现，保持不动） ──

def _transcribe_chunk_volc(
    index: int,
    start: float,
    chunk_path: Path,
    settings,
    request_timeout: float = 120.0,
    retries: int = 1,
) -> dict[str, object]:
    """用火山 flash 极速识别转写一个音频分片。"""
    started = time.perf_counter()
    request_deadline = started + max(1.0, request_timeout)
    error = "unknown error"
    api_calls = 0
    for attempt in range(retries + 1):
        request_remaining = request_deadline - time.perf_counter()
        if request_remaining <= 1:
            error = "ASR request budget exhausted"
            break
        try:
            api_calls += 1
            headers = settings.asr_headers
            if headers is None:
                raise AsrError(
                    "ASR 凭证未配置：请在 agent设置页填写火山引擎语音技术 "
                    "API Key（或 App ID + Access Token），或配置 .env 的 VOLC_ASR_*"
                )
            headers = {**headers, "Content-Type": "application/json"}

            payload: dict[str, object] = {
                "user": {"uid": _volc_user_id()},
                "audio": {
                    "data": base64.b64encode(chunk_path.read_bytes()).decode("ascii")
                },
                "request": {"model_name": settings.asr_model or "bigmodel"},
            }

            # trust_env=False：外部服务直连为受控策略，不继承环境代理（规范 07 §4）
            with httpx.Client(timeout=max(5.0, request_remaining), trust_env=False) as client:
                response = client.post(VOLC_RECOGNIZE_URL, json=payload, headers=headers)

            status_code = int(response.headers.get("X-Api-Status-Code") or 0)
            body = response.json() if response.content else {}
            header_code = int(((body.get("header") or {}).get("code")) or 0)

            if response.status_code != 200:
                raise AsrError(
                    f"ASR HTTP {response.status_code}: "
                    f"{body.get('header', {}).get('message') or response.text[:300]}"
                )
            if status_code and status_code != 20000000:
                message = response.headers.get("X-Api-Message") or body.get("header", {}).get("message") or ""
                if status_code in (20000003, 45000002):
                    # 静音/空音频：不是凭证错误，视为成功（无内容）
                    result = {"text": "", "utterances": []}
                else:
                    raise AsrError(f"ASR 失败({status_code}): {message}")
            elif header_code and header_code not in (0, 20000000):
                if header_code in (20000003, 45000002):
                    result = {"text": "", "utterances": []}
                else:
                    raise AsrError(
                        f"ASR 失败({header_code}): {body.get('header', {}).get('message')}"
                    )
            else:
                result = body.get("result") or {}

            utterances = list(result.get("utterances") or [])
            entries = format_utterance_entries(utterances, chunk_start=start)
            all_text = "\n".join(f"[{format_time(sec)}] {txt}" for sec, txt in entries)

            return {
                "index": index,
                "start": start,
                "text": all_text,
                "raw_utterances": utterances,
                "language": None,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "attempts": api_calls,
                "error": None,
            }
        except AsrError as exc:
            error = _redact_vendor_error(exc, settings)
            # 凭证/权限类错误不重试
            if any(k in error for k in ("401", "403", "未配置", "没有权限", "InvalidParameter")):
                break
            if attempt < retries:
                time.sleep(min(0.5 * (attempt + 1), max(0, request_deadline - time.perf_counter())))
        except Exception as exc:  # noqa: BLE001 — 网络/超时等，统一进入重试
            error = _redact_vendor_error(exc, settings)
            if attempt < retries:
                time.sleep(min(0.5 * (attempt + 1), max(0, request_deadline - time.perf_counter())))
    return {
        "index": index,
        "start": start,
        "text": "",
        "language": None,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "attempts": api_calls,
        "error": error,
    }


# ── 双渠道分发入口（保持对外签名不变） ──

def transcribe_chunk(
    index: int,
    start: float,
    chunk_path: Path,
    settings,
    request_timeout: float = 120.0,
    retries: int = 1,
) -> dict[str, object]:
    """按 settings.asr_provider 选择 ASR 渠道转写一个音频分片。"""
    provider = (settings.asr_provider or "volcengine").strip().lower()
    if provider in DASHSCOPE_PROVIDERS:
        return _transcribe_chunk_dashscope(
            index, start, chunk_path, settings, request_timeout, retries
        )
    return _transcribe_chunk_volc(
        index, start, chunk_path, settings, request_timeout, retries
    )


def test_asr_connection(settings, timeout: float = 30.0) -> tuple[bool, str]:
    """验证当前渠道的 ASR 凭证/模型可用；静音音频成功也算连接通过。"""
    provider = (settings.asr_provider or "volcengine").strip().lower()
    if provider in DASHSCOPE_PROVIDERS:
        return _test_asr_connection_dashscope(settings, timeout)
    return _test_asr_connection_volc(settings, timeout)


def _test_asr_connection_volc(settings, timeout: float = 30.0) -> tuple[bool, str]:
    """用一段极短静音音频验证火山 flash 凭证/模型/资源权限可用。"""
    import wave

    headers = settings.asr_headers
    if headers is None:
        return False, "ASR 凭证未配置：请在 agent设置页填写 API Key 或 App ID + Access Token"
    # 生成 0.3s 静音 wav（16k 单声道 16bit）
    import io
    import math
    import struct

    sr = 16000
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(
            struct.pack("<h", int(1200 * math.sin(2 * math.pi * 440 * i / sr)))
            for i in range(int(sr * 0.3))
        ))
    try:
        payload: dict[str, object] = {
            "user": {"uid": _volc_user_id()},
            "audio": {"data": base64.b64encode(buf.getvalue()).decode("ascii")},
            "request": {"model_name": settings.asr_model or "bigmodel"},
        }
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            response = client.post(
                VOLC_RECOGNIZE_URL,
                json=payload,
                headers={**headers, "Content-Type": "application/json"},
            )
        status_code = int(response.headers.get("X-Api-Status-Code") or 0)
        if response.status_code == 200 and status_code in (0, 20000000, 20000003, 45000002):
            return True, "连接成功（ASR 凭证与模型可用）"
        body = {}
        try:
            body = response.json()
        except Exception:  # noqa: BLE001
            pass
        message = (
            response.headers.get("X-Api-Message")
            or (body.get("header") or {}).get("message")
            or response.text[:200]
        )
        return False, "连接失败: " + _redact_vendor_error(
            message or f"HTTP {response.status_code}", settings
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"连接失败: {_redact_vendor_error(exc, settings)}"


def _test_asr_connection_dashscope(settings, timeout: float = 60.0) -> tuple[bool, str]:
    """下载一段含语音的样例音频 → 送入百炼 → 提交 filetrans → 轮询，验证整链路。

    送入方式跟随 settings.asr_upload_mode：
    - oss：直传 OSS 拿 oss:// 临时 URL（默认，本地无需公网入口）
    - public-url：经应用 capability URL 暴露
    使用官方 OSS 样例（含语音），能真正识别出句子；空音频/无语音也视为连接通过。
    """
    api_key = (settings.asr_api_key or "").strip()
    if not api_key:
        return False, "ASR 凭证未配置：请在 agent设置页填写百炼 API Key（DASHSCOPE_ASR_API_KEY）"
    model = (settings.asr_model or DASHSCOPE_ASR_MODEL_DEFAULT).strip()
    endpoint = (settings.asr_endpoint or "").strip() or DASHSCOPE_SUBMIT_URL
    upload_mode = (getattr(settings, "asr_upload_mode", "") or "oss").strip().lower()
    use_oss = upload_mode != "public-url"

    public_base_url = ""
    if not use_oss:
        public_base_url = (settings.asr_public_base_url or "").strip()
        if not public_base_url:
            return False, (
                "未配置 DashScope 媒体入口：请设置 DASHSCOPE_ASR_PUBLIC_BASE_URL，"
                "或改用 ASR_UPLOAD_MODE=oss"
            )

    sample_url = os.environ.get(
        "DASHSCOPE_ASR_TEST_AUDIO",
        # 含人声的官方样例（welcome.mp3 是纯音乐，识别不出句子）
        "https://dashscope.oss-cn-beijing.aliyuncs.com/samples/audio/paraformer/"
        "hello_world_female.wav",
    )
    public_file: Path | None = None
    media_token: str | None = None
    try:
        with httpx.Client(timeout=min(30.0, timeout), trust_env=False) as client:
            resp = client.get(sample_url)
            if resp.status_code != 200:
                return False, f"测试音频下载失败 HTTP {resp.status_code}"
            audio_bytes = resp.content
        if use_oss:
            public_dir = _public_dir()
            public_dir.mkdir(parents=True, exist_ok=True)
            suffix = Path(sample_url.split("?")[0]).suffix or ".wav"
            public_file = public_dir / f"asr_test_{uuid.uuid4().hex}{suffix}"
            public_file.write_bytes(audio_bytes)
            file_url = _dashscope_upload_via_policy(public_file, model, api_key)
        else:
            public_dir = _public_dir()
            public_dir.mkdir(parents=True, exist_ok=True)
            public_file = public_dir / f"asr_test_{uuid.uuid4().hex}.wav"
            public_file.write_bytes(audio_bytes)
            media_token, file_url = register_dashscope_media(
                public_file, public_base_url, ttl_seconds=timeout + 60
            )
        deadline = time.perf_counter() + max(10.0, timeout)
        task_id = _dashscope_submit(model, file_url, api_key, endpoint, oss=use_oss)
        sentences = _dashscope_poll_and_fetch(task_id, api_key, deadline)
        mode_hint = "OSS 直传" if use_oss else "公网入口"
        if sentences:
            sample = str(sentences[0].get("text") or "")[:40]
            return True, (
                f"连接成功（百炼可用 · {mode_hint}，模型 {model}，"
                f"识别 {len(sentences)} 句，首句: {sample}）"
            )
        return True, f"连接成功（百炼可用 · {mode_hint}，测试音频未含可识别语音）"
    except AsrError as exc:
        return False, f"连接失败: {_redact_vendor_error(exc, settings)}"
    except Exception as exc:  # noqa: BLE001
        return False, f"连接失败: {_redact_vendor_error(exc, settings)}"
    finally:
        unregister_dashscope_media(media_token)
        if public_file is not None:
            try:
                public_file.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
