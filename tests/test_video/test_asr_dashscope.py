"""百炼（dashscope）渠道的解析与传入方式回归测试。

锁死两条在实测中踩到的真实 bug：
1. `_extract_sentences` 必须优先取 `transcripts[].sentences[]`。
   旧实现按 ("sentences","utterances","results") 递归，会先命中 `results` ——
   而 `output.results[].results` 是**空数组**，导致 3.x 模型永远识别出 0 句
   （提交/轮询都成功、文本却是空的，静默失败）。
2. `_sentence_times` 必须按**键名**判定单位。3.x 的 begin_time/end_time 是**毫秒**；
   旧实现用「值 > 1000 才当毫秒」猜，短音频首句起点 120ms 会被当成 120 秒。
"""
from __future__ import annotations

from pathlib import Path

from src.video import asr
from src.video.settings import VideoAgentSettings


# ── 1. 句子提取 ──

# 实测抓到的真实 3.x 结果结构
REAL_3X = {
    "file_url": "http://x/y.wav",
    "properties": {"audio_format": "pcm_s16le", "channels": [0]},
    "transcripts": [
        {
            "channel_id": 0,
            "text": "hello world，来自阿里巴巴达摩院语音实验室。",
            "sentences": [
                {
                    "begin_time": 120,
                    "end_time": 4000,
                    "text": "hello world，来自阿里巴巴达摩院语音实验室。",
                    "sentence_id": 1,
                }
            ],
        }
    ],
}


def test_extract_sentences_from_transcripts() -> None:
    """3.x 的 transcripts[].sentences[] 必须被取到。"""
    out = asr._extract_sentences(REAL_3X)
    assert len(out) == 1
    assert out[0]["text"] == "hello world，来自阿里巴巴达摩院语音实验室。"


def test_extract_sentences_not_fooled_by_empty_results() -> None:
    """轮询响应里 output.results[].results 是空数组，不能因此提前返回 []。"""
    noisy = {
        "output": {
            "results": [{"results": [], "subtask_status": "SUCCEEDED"}],
            "output": REAL_3X,
        }
    }
    out = asr._extract_sentences(noisy)
    assert len(out) == 1, "空 results 数组不得遮蔽真实的 sentences"


def test_extract_sentences_multi_channel() -> None:
    """多音轨：每个 channel 的句子都要收上来。"""
    multi = {
        "transcripts": [
            {"channel_id": 0, "sentences": [{"text": "A1", "begin_time": 0, "end_time": 1}]},
            {"channel_id": 1, "sentences": [{"text": "B1", "begin_time": 0, "end_time": 1}]},
        ]
    }
    assert [s["text"] for s in asr._extract_sentences(multi)] == ["A1", "B1"]


def test_extract_sentences_volc_style_still_works() -> None:
    """回归保护：火山风格 utterances 仍能提取。"""
    volc = {"result": {"utterances": [{"text": "火山句", "start_time": 0, "end_time": 100}]}}
    assert [s["text"] for s in asr._extract_sentences(volc)] == ["火山句"]


def test_extract_sentences_empty() -> None:
    assert asr._extract_sentences({"transcripts": [{"sentences": []}]}) == []


# ── 2. 时间戳单位 ──


def test_sentence_times_milliseconds_for_begin_time() -> None:
    """3.x：begin_time/end_time 是毫秒 → 必须除以 1000。"""
    begin, end = asr._sentence_times({"begin_time": 120, "end_time": 4000})
    assert begin == 0.12
    assert end == 4.0


def test_sentence_times_short_audio_not_misread_as_seconds() -> None:
    """关键回归：120ms 不得被当成 120 秒（旧实现按数值大小猜单位时会错）。"""
    begin, _ = asr._sentence_times({"begin_time": 120, "end_time": 4000})
    assert begin < 1.0, f"120ms 被误判为 {begin}s"


def test_sentence_times_seconds_for_start_time() -> None:
    """旧兼容路径：start_time 是秒，不换算。"""
    begin, end = asr._sentence_times({"start_time": 1.5, "end_time": 3.0})
    assert begin == 1.5
    assert end == 3.0


def test_dashscope_entries_produce_timestamps() -> None:
    """端到端到条目：文本带 [MM:SS] 前缀且时间正确。"""
    entries = asr._dashscope_sentences_to_entries(
        [{"begin_time": 120, "end_time": 4000, "text": "hello"}], 0.0
    )
    assert entries == [(0.12, "hello")]


# ── 3. input 字段按模型族分支 ──


def test_input_payload_multi_url_for_audio_3x() -> None:
    assert asr._dashscope_input_payload("qwen-audio-3.1-asr-flash-filetrans", "oss://a/b.wav") == {
        "file_urls": ["oss://a/b.wav"]
    }
    assert asr._dashscope_input_payload("qwen-audio-3.0-asr-flash-filetrans", "x") == {
        "file_urls": ["x"]
    }
    assert asr._dashscope_input_payload("fun-asr-2025-08-25", "x") == {"file_urls": ["x"]}


def test_input_payload_single_url_for_qwen3() -> None:
    assert asr._dashscope_input_payload("qwen3-asr-flash-filetrans", "https://a/b.mp3") == {
        "file_url": "https://a/b.mp3"
    }


# ── 4. OSS 传入方式 ──


def test_oss_resolve_header_value() -> None:
    """oss:// 必须带解析头，值固定 enable。"""
    assert asr.OSS_RESOLVE_HEADER == {"X-DashScope-OssResourceResolve": "enable"}


def test_upload_to_oss_puts_file_last_and_builds_key(tmp_path: Path, monkeypatch) -> None:
    """multipart 表单：file 必须最后、字段名与大小写须正确、返回 oss:// 前缀 URL。"""
    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFFfake")
    captured: dict = {}

    class Response:
        status_code = 200
        text = ""

    class Client:
        def __init__(self, *a, **kw) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, files=None):
            captured["url"] = url
            captured["files"] = files
            return Response()

    monkeypatch.setattr(asr.httpx, "Client", Client)

    policy = {
        "upload_host": "https://oss.example.test",
        "upload_dir": "dashscope-instant/abc/2026-09-22/xyz",
        "policy": "POL",
        "signature": "SIG",
        "oss_access_key_id": "AK",
        "x_oss_object_acl": "private",
        "x_oss_forbid_overwrite": "true",
    }
    url = asr._dashscope_upload_to_oss(policy, audio, "sk-test")

    assert url == "oss://dashscope-instant/abc/2026-09-22/xyz/chunk.wav"
    assert captured["url"] == "https://oss.example.test"
    names = [f[0] for f in captured["files"]]
    assert names[-1] == "file", f"file 必须是最后一个表单域，实际：{names}"
    assert names[:3] == ["OSSAccessKeyId", "policy", "Signature"]
    assert "x-oss-object-acl" in names
    assert "x-oss-forbid-overwrite" in names


def test_upload_failure_raises(tmp_path: Path, monkeypatch) -> None:
    """OSS 返回非 2xx 必须抛错（而不是静默当成功）。"""
    audio = tmp_path / "c.wav"
    audio.write_bytes(b"x")

    class Response:
        status_code = 403
        text = "<Error>AccessDenied</Error>"

    class Client:
        def __init__(self, *a, **kw) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, files=None):
            return Response()

    monkeypatch.setattr(asr.httpx, "Client", Client)
    policy = {"upload_host": "https://oss.test", "upload_dir": "d", "policy": "p"}
    try:
        asr._dashscope_upload_to_oss(policy, audio, "k")
    except asr.AsrError as exc:
        assert "403" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("403 未抛出 AsrError")


# ── 5. 默认值与上传模式 ──


def test_default_model_is_audio_31() -> None:
    from src.video.settings import DASHSCOPE_ASR_MODEL_DEFAULT

    assert DASHSCOPE_ASR_MODEL_DEFAULT == "qwen-audio-3.1-asr-flash-filetrans"


def test_upload_mode_defaults_to_oss() -> None:
    """默认必须走 oss —— public-url 需要公网入口，本地跑不通。"""
    s = VideoAgentSettings()
    assert s.asr_upload_mode == "oss"
