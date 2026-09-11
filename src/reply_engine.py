# -*- coding: utf-8 -*-
"""回复决策引擎（纯逻辑）：判断某位好友的最新消息是否需要 AI 回复。

规则：
1. 只处理白名单好友（由调用方保证）。
2. 最新一条消息是自己发的 -> 不回复（等对方先说）。
3. 最新一条是对方发的：
   - 图片消息（网页版能读到图片元素）-> 需要回复，交给视觉模型看图后回复。
   - 没有文字也没有图片（语音/部分卡片等，网页版只显示占位文案）且 skip_non_text=True
     -> 跳过并记为已处理，避免反复打扰。
   - 文字消息：指纹和上次已处理的一致 -> 跳过（不会重复回复同一句话）。
   - 以上回复都要过频率限制。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from state_store import msg_fingerprint

# 抖音网页版对某些消息类型（语音/部分卡片等）只显示占位文案，无法看到真实内容。
# 这些也算“非文字、非图片”，不应拿去让 AI 回复。
DOUYIN_UNSUPPORTED_MARKERS = (
    "暂不支持该消息类型",
    "暂不支持",
    "请到抖音手机端查看",
)

KIND_TEXT = "text"
KIND_IMAGE = "image"
KIND_UNSUPPORTED = "unsupported"

NON_TEXT_FP = msg_fingerprint("__non_text__")


class Decision:
    def __init__(self, action: str, reason: str, incoming_text: str = "", fingerprint: str = "",
                 kind: str = KIND_TEXT) -> None:
        self.action = action          # reply | skip | nothing
        self.reason = reason
        self.incoming_text = incoming_text
        self.fingerprint = fingerprint
        self.kind = kind              # text | image

    def to_dict(self) -> dict[str, str]:
        return {"action": self.action, "reason": self.reason,
                "incoming_text": self.incoming_text, "fingerprint": self.fingerprint,
                "kind": self.kind}


def _rate_count(events: list[str], window: timedelta, now: datetime) -> int:
    if not events:
        return 0
    cutoff = now - window
    return sum(1 for e in events if _parse(e) >= cutoff)


def _parse(iso: str) -> datetime:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            return dt.astimezone()
        return dt
    except Exception:
        # 必须返回带时区的最小值，否则与 aware 的 cutoff 比较会抛 TypeError
        return datetime.min.replace(tzinfo=timezone.utc)


def message_kind(msg: dict[str, Any]) -> str:
    """判断一条消息是 文字 / 图片 / 不支持(语音卡片等)。"""
    kind = str(msg.get("kind") or "")
    if kind == KIND_IMAGE:
        return KIND_IMAGE
    text = str(msg.get("text", "")).strip()
    if (not text) or any(m in text for m in DOUYIN_UNSUPPORTED_MARKERS):
        return KIND_UNSUPPORTED
    return KIND_TEXT


def _within_rate_limit(friend_state: dict[str, Any], reply_cfg: dict[str, Any], now: datetime) -> tuple[bool, str]:
    hour_events = friend_state.get("replied_at", [])
    if reply_cfg.get("max_per_friend_per_hour", 0) > 0:
        count = _rate_count(hour_events, timedelta(hours=1), now)
        if count >= int(reply_cfg["max_per_friend_per_hour"]):
            return False, "达到每小时回复上限，本轮跳过"
    day_events = friend_state.get("replied_at_day", hour_events)
    if reply_cfg.get("max_per_friend_per_day", 0) > 0:
        count = _rate_count(day_events, timedelta(days=1), now)
        if count >= int(reply_cfg["max_per_friend_per_day"]):
            return False, "达到每天回复上限，本轮跳过"
    return True, ""


def _repeat_window_elapsed(friend_state: dict[str, Any], reply_cfg: dict[str, Any], now: datetime) -> bool:
    """同指纹（相同文字/相同图片）消息过了宽限期就算“新消息”。

    红点出现且最新一条和上次已回复的内容相同，通常是对方真的又发了一句
    一样的话（“?”、“在吗”这类很常见）；但红点未消的界面异常也会造成
    同样现象。用时间窗区分：宽限期内一律视为重复（防连环回复），
    超过 repeat_same_text_after_minutes 分钟才允许再回一次。
    配 0（旧默认）= 永不重复回复同内容。
    """
    minutes = float(reply_cfg.get("repeat_same_text_after_minutes", 0) or 0)
    if minutes <= 0:
        return False
    last_at = _parse(str(friend_state.get("last_replied_at") or ""))
    if last_at.tzinfo is None:
        return False
    return (now - last_at).total_seconds() >= minutes * 60


def decide_reply(
    *,
    friend: str,
    messages: list[dict[str, Any]],       # 最新在前
    friend_state: dict[str, Any],
    reply_cfg: dict[str, Any],
    now: datetime | None = None,
) -> Decision:
    now = now or datetime.now().astimezone()

    if not messages:
        return Decision("nothing", "没有读到任何消息")

    newest = messages[0]
    newest_from_me = bool(newest.get("from_me"))
    kind = message_kind(newest)
    newest_text = str(newest.get("text", "")).strip()

    if newest_from_me:
        # 对方还没回我们，等下一轮
        return Decision("nothing", "最新一条是自己发的，等对方回复")

    # ── 图片消息：需要 AI 看图后回复 ────────────────────────
    if kind == KIND_IMAGE:
        image_cfg = reply_cfg.get("images", {})
        if not image_cfg.get("enabled", True):
            return Decision("nothing", "图片消息回复已关闭（reply.images.enabled=false），仅监视不回复")
        if str(image_cfg.get("policy", "vision")).strip().lower() == "skip":
            return Decision("skip", "图片消息策略为 skip：跳过且记为已处理", fingerprint=NON_TEXT_FP)
        # 用图片本身做指纹（data:URL 或图片地址各不相同），避免同一张图重复回
        img_src = str(newest.get("img_src") or "")
        img_key = img_src if img_src else "unknown-image"
        fp = msg_fingerprint(f"__image__|{img_key}")
        if friend_state.get("last_replied_fp") == fp and not _repeat_window_elapsed(friend_state, reply_cfg, now):
            return Decision("nothing", "这张图片已经处理过")
        ok, reason = _within_rate_limit(friend_state, reply_cfg, now)
        if not ok:
            return Decision("nothing", reason)
        return Decision("reply", "对方发来一张图片，需要 AI 回复",
                        incoming_text="[图片]", fingerprint=fp, kind=KIND_IMAGE)

    # ── 不支持的消息类型（语音/卡片等，无图无文字） ──────────
    if kind == KIND_UNSUPPORTED:
        if friend_state.get("last_replied_fp") == NON_TEXT_FP:
            return Decision("nothing", "最新消息仍是非文字/不支持类型，已处理过")
        if reply_cfg.get("skip_non_text", True):
            return Decision("skip", "最新消息不是可回复内容（语音/图片表情未显示或网页版不支持的类型），跳过且记为已处理",
                            fingerprint=NON_TEXT_FP)
        return Decision("nothing", "最新消息不是可回复内容，不回复")

    # ── 文字消息 ────────────────────────────────────────────
    fp = msg_fingerprint(newest_text)
    if friend_state.get("last_replied_fp") == fp and not _repeat_window_elapsed(friend_state, reply_cfg, now):
        return Decision("nothing", "这条对方消息已经处理过")

    ok, reason = _within_rate_limit(friend_state, reply_cfg, now)
    if not ok:
        return Decision("nothing", reason)

    return Decision("reply", "对方发来新消息，需要 AI 回复", incoming_text=newest_text, fingerprint=fp)
