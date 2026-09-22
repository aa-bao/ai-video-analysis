"""摘要 max_tokens 截断 bug 回归测试。

真实踩过的坑（2026-09-22，任务 8d3f956a676f4128）：
``deepseek-flash`` 是**推理模型** —— ``max_tokens=2000`` 里 ~1891 是 reasoning_tokens，
真正留给 JSON 的只剩约 109 tokens，正文被**拦腰截断**（finish_reason=length）。
``_extract_json`` 的 ``rfind("}")`` 找不到收尾括号 → 返回 None → 归一化成空摘要。
现象极具迷惑性：title 有值（回填 title_hint）、mode=summary，看起来像成功。

这组测试锁两件事：
1. 截断的 JSON 必须被 ``_extract_json`` 判定为失败（而不是拼出半个对象）；
2. 输出预算足够容纳「思维链 + 正文」，且可由环境变量覆盖。
"""
from __future__ import annotations

from src.video.summary import (
    _DEFAULT_SUMMARY_MAX_TOKENS,
    _extract_json,
    _summary_max_tokens,
    _normalize_summary,
)

# 实测录到的截断样本（deepseek-flash, max_tokens=2000, finish_reason=length）
TRUNCATED = (
    '{"title":"Shiro：绿龙体系下的聪明实用型狙击手","summary":'
    '"视频解析 CS 顶级狙击手 Shiro 在绿龙（Team Spirit）体系中的特殊定位与打法。'
    '他并非只会被动逃狙，而是依靠思路和局势分析，常处中后段、可抽离队伍打残局。'
    '绿龙信任并给予他空间，他也用道具、走位、兜底和残局能力增加团队厚度。'
    '片中还用多个回合说明其实用主义与临场反应，'
)


def test_truncated_json_is_rejected_not_partially_parsed() -> None:
    # 关键断言：截断样本必须解析失败，绝不能返回一个"摘要有值但要点为空"的假成功
    assert _extract_json(TRUNCATED) is None


def test_truncated_response_normalizes_to_empty_summary() -> None:
    """记录 bug 的实际表现：截断 → 空摘要 + title 回填 title_hint。"""
    data = _extract_json(TRUNCATED) or {}
    summary = _normalize_summary(data, title_hint="真实视频标题", keyframes=[])

    # 修复前的症状（保留此断言，说明修复前会发生什么）
    assert summary["summary"] == ""
    assert summary["keypoints"] == []
    # title 回填 hint —— 正是这行让调用方误以为"摘要成功"
    assert summary["title"] == "真实视频标题"
    assert summary["mode"] == "summary"


def test_complete_json_parses_and_keeps_summary(tmp_path=None) -> None:
    """对照组：完整 JSON 必须正常解析。"""
    complete = (
        '{"title":"标题","summary":"一段摘要。",'
        '"keypoints":["要点一","要点二"]}'
    )
    data = _extract_json(complete)
    assert data is not None
    summary = _normalize_summary(data, title_hint="hint", keyframes=[])
    assert summary["summary"] == "一段摘要。"
    assert summary["keypoints"] == ["要点一", "要点二"]


def test_default_budget_covers_reasoning_plus_body() -> None:
    """默认预算必须远大于 reasoning 开销（实测 reasoning ≈1600-1900）。"""
    assert _DEFAULT_SUMMARY_MAX_TOKENS >= 4000
    assert _summary_max_tokens() == _DEFAULT_SUMMARY_MAX_TOKENS


def test_budget_overridable_by_env(monkeypatch) -> None:
    monkeypatch.setenv("VIDEO_SUMMARY_MAX_TOKENS", "12000")
    assert _summary_max_tokens() == 12000


def test_invalid_env_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setenv("VIDEO_SUMMARY_MAX_TOKENS", "not-a-number")
    assert _summary_max_tokens() == _DEFAULT_SUMMARY_MAX_TOKENS
    monkeypatch.setenv("VIDEO_SUMMARY_MAX_TOKENS", "-5")
    assert _summary_max_tokens() == _DEFAULT_SUMMARY_MAX_TOKENS
