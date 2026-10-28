"""QQ 红包提醒：白名单群出现红包时，只私聊主人。

设计目标：
- 不领取、不在群里发言、不调用 LLM，零 token；
- 只监听配置里的群；
- 兼容 aiocqhttp/OneBot v11，优先用 NapCat 私聊，失败回退 AstrBot 会话；
- 同一红包 10 秒内只提醒一次。
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import MessageChain, filter
from astrbot.api.event.filter import EventMessageType
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star, register
from astrbot.core.platform.message_session import MessageSession

DEFAULT_TEMPLATE = (
    "💰 红包提醒\n"
    "群：{group_name}（{group_id}）\n"
    "发送者：{sender_name}（{sender_id}）\n"
    "时间：{time}\n"
    "快去抢！"
)


@register("astrbot_plugin_redalert", "dafeiyu", "QQ 红包提醒", "1.0.0")
class QQRedAlert(Star):
    def __init__(self, context: Context, config: AstrBotConfig | dict | None = None):
        super().__init__(context)
        self.conf = config or {}
        self.enabled = bool(self.conf.get("enabled", True))
        self.debug = bool(self.conf.get("debug", False))
        self.bot_qq = str(self.conf.get("bot_qq", "") or "").strip()
        self.allow_password = bool(self.conf.get("allow_password_redpacket", False))
        ex = self.conf.get("exclude_keywords") or ["已领完", "已过期", "手慢了", "来晚了"]
        if isinstance(ex, str):
            ex = re.split(r"[,;\s]+", ex)
        self.exclude_keywords = [str(x) for x in ex if str(x).strip()]
        owners = self.conf.get("owner_ids") or []
        if isinstance(owners, str):
            owners = re.split(r"[,;\s]+", owners)
        if not owners and self.conf.get("owner_id"):
            owners = [self.conf.get("owner_id")]
        self.owner_ids = [str(x).strip() for x in owners if str(x).strip()]
        groups = self.conf.get("watch_groups") or []
        if isinstance(groups, str):
            groups = re.split(r"[,;\s]+", groups)
        self.watch_groups = {str(g).strip() for g in groups if str(g).strip()}
        self.template = str(self.conf.get("notify_template") or DEFAULT_TEMPLATE).replace("\\n", "\n")
        self.seen: dict[str, float] = {}
        if not self.owner_ids:
            logger.warning("[redalert] 未配置 owner_id / owner_ids，红包提醒不会发送")
        if not self.watch_groups:
            logger.warning("[redalert] watch_groups 为空，不会监听任何群")

    def _is_owner(self, event) -> bool:
        try:
            return str(event.get_sender_id()) in self.owner_ids
        except Exception:
            return False

    @staticmethod
    def _raw_segments(event):
        raw = getattr(event.message_obj, "raw_message", None)
        if isinstance(raw, dict):
            yield from raw.get("message", [])
        else:
            msg = getattr(raw, "message", None)
            if isinstance(msg, list):
                yield from msg

    @staticmethod
    def _has_red_marker(blob: str) -> bool:
        b = (blob or "").lower()
        if "__napcat_wallet" in b:
            return any(
                k in b
                for k in ("redchannel", "billno", "pcbody", "redbag", "redpacket", "grab")
            )
        return any(
            k in b
            for k in (
                "com.tencent.mobileqq.redpacket",
                "redpacket",
                "redbag",
                "red_bag",
                "qredpacket",
                "grabredbag",
            )
        )

    def _is_red_packet(self, event, msg: str) -> bool:
        text = (msg or "").strip()
        # 只认 QQ 红包的固定展示文本，不认普通聊天里的“红包”两个字
        if text in ("[QQ红包]", "QQ红包") or text.startswith("[QQ红包]"):
            return True
        # 真正的红包卡片：只检查 json/xml 结构里的红包标记
        for seg in self._raw_segments(event):
            try:
                if not isinstance(seg, dict):
                    continue
                if str(seg.get("type", "")).lower() not in ("json", "xml"):
                    continue
                data = seg.get("data", {})
                if self._has_red_marker(json.dumps(data, ensure_ascii=False)):
                    return True
            except Exception:
                continue
        try:
            for comp in event.get_messages():
                d = comp.toDict() if hasattr(comp, "toDict") else {}
                if str(d.get("type", "")).lower() in ("json", "xml"):
                    if self._has_red_marker(json.dumps(d, ensure_ascii=False)):
                        return True
        except Exception:
            pass
        if self.debug and "红包" in text and not text.startswith("/"):
            raw = str(getattr(event.message_obj, "raw_message", ""))[:500]
            logger.info(f"[redalert] 未识别为红包卡片: text={text[:80]!r} raw={raw!r}")
        return False

    def _event_blob(self, event, msg: str) -> str:
        parts = [msg or ""]
        for seg in self._raw_segments(event):
            try:
                parts.append(json.dumps(seg, ensure_ascii=False))
            except Exception:
                parts.append(str(seg))
        try:
            for comp in event.get_messages():
                d = comp.toDict() if hasattr(comp, "toDict") else {}
                parts.append(json.dumps(d, ensure_ascii=False))
        except Exception:
            pass
        return "\n".join(parts)

    def _extract_wallet(self, event):
        for seg in self._raw_segments(event):
            try:
                if not isinstance(seg, dict) or str(seg.get("type", "")).lower() != "json":
                    continue
                data = seg.get("data", {})
                payload = data.get("data") if isinstance(data, dict) else data
                if not isinstance(payload, str):
                    continue
                obj = json.loads(payload)
                if isinstance(obj, dict) and obj.get("__napcat_wallet"):
                    return obj
            except Exception:
                continue
        try:
            for comp in event.get_messages():
                d = comp.toDict() if hasattr(comp, "toDict") else {}
                if str(d.get("type", "")).lower() != "json":
                    continue
                data = d.get("data", {})
                payload = data.get("data") if isinstance(data, dict) else data
                if isinstance(payload, str):
                    obj = json.loads(payload)
                    if isinstance(obj, dict) and obj.get("__napcat_wallet"):
                        return obj
        except Exception:
            pass
        return None

    def _is_claimable(self, event, msg: str) -> bool:
        blob = self._event_blob(event, msg).lower()
        # 已领完 / 过期 / 来晚
        if any(k.lower() in blob for k in self.exclude_keywords):
            return False
        # 口令红包：默认不提醒，除非显式允许
        if not self.allow_password:
            if "口令" in blob or '"redchannel": 32' in blob or '"redchannel":32' in blob:
                return False

        wallet = self._extract_wallet(event)
        if wallet:
            receiver = wallet.get("receiver") or {}
            content = str(receiver.get("content", "")) + str(receiver.get("notice", ""))
            if "红包" not in content:
                return False
            try:
                if int(wallet.get("grabState", 0) or 0) != 0:
                    return False
            except Exception:
                return False
            amount = str(wallet.get("grabbedAmount", "0") or "0")
            if amount not in ("0", "0.0"):
                return False
            grap = wallet.get("grapUin") or []
            if isinstance(grap, (str, int)):
                grap = [grap]
            grap = [str(x).strip() for x in grap if str(x).strip()]
            if grap and (not self.bot_qq or self.bot_qq not in grap):
                return False
            return True

        # 非 NapCat 钱包结构：退回通用过滤
        if "专属" in blob:
            if not self.bot_qq or self.bot_qq not in blob:
                return False
        return True

    def _dedup(self, key: str) -> bool:
        now = time.time()
        self.seen = {k: v for k, v in self.seen.items() if now - v < 60}
        if key in self.seen and now - self.seen[key] < 10:
            return False
        self.seen[key] = now
        return True

    async def _send_owner(self, event, text: str) -> bool:
        for owner in self.owner_ids:
            # 优先 NapCat 私聊
            try:
                client = event.bot
                await client.api.call_action(
                    "send_private_msg",
                    user_id=int(owner),
                    message=text,
                )
                return True
            except Exception as e:
                logger.debug(f"[redalert] NapCat 私聊 {owner} 失败: {e}")
            # 回退 AstrBot 会话发送
            try:
                session = MessageSession.from_str(f"qq:FriendMessage:{owner}")
                await self.context.send_message(session, MessageChain([Plain(text)]))
                return True
            except Exception as e:
                logger.error(f"[redalert] 私聊 {owner} 失败: {e}")
        return False

    @filter.event_message_type(EventMessageType.ALL, priority=sys.maxsize - 5)
    async def on_message(self, event):
        if not self.enabled:
            return
        try:
            msg = event.message_str or ""
            gid0 = str(event.get_group_id() or "")
            if self.debug and gid0 in self.watch_groups:
                logger.info(
                    f"[redalert][debug] gid={gid0} text={msg[:80]!r} "
                    f"raw={self._event_blob(event, msg)[:1800]!r}"
                )
            if not self._is_red_packet(event, msg):
                return
            gid = str(event.get_group_id() or "")
            if gid not in self.watch_groups:
                return
            sender = str(event.get_sender_id() or "")
            if sender == str(event.get_self_id() or ""):
                return
            if not self._is_claimable(event, msg):
                if self.debug:
                    logger.info(f"[redalert] 红包不可领取/非本机专属，跳过: {msg[:60]!r}")
                return
            if self.debug:
                blob = self._event_blob(event, msg)[:1200]
                logger.info(f"[redalert] 命中红包卡片 text={msg[:60]!r} raw={blob!r}")

            mid = str(getattr(event.message_obj, "message_id", "") or "")
            key = f"{gid}:{mid}:{sender}:{msg[:20]}"
            if not self._dedup(key):
                return

            group_name = ""
            try:
                g = event.message_obj.group
                if g:
                    group_name = g.group_name or ""
            except Exception:
                pass
            text = self.template.format(
                group_name=group_name or "未知群",
                group_id=gid,
                sender_name=event.get_sender_name() or "未知",
                sender_id=sender,
                time=datetime.now().strftime("%H:%M:%S"),
            )
            ok = await self._send_owner(event, text)
            logger.info(f"[redalert] 群 {gid} 发现红包，提醒{'成功' if ok else '失败'}")
        except Exception as e:
            logger.error(f"[redalert] 处理红包消息失败: {e}")

    @filter.command("红包测试")
    async def test_cmd(self, event):
        if not self._is_owner(event):
            yield event.plain_result("这个只有主人能测。")
            return
        ok = await self._send_owner(
            event,
            "💰 红包提醒测试\n如果你收到这条私聊，说明红包提醒链路是通的。",
        )
        yield event.plain_result("测试提醒已发送。" if ok else "测试提醒发送失败，检查私聊配置。")

    @filter.command("红包状态")
    async def status_cmd(self, event):
        if not self._is_owner(event):
            yield event.plain_result("这个只有主人能看。")
            return
        yield event.plain_result(
            "红包提醒状态\n"
            f"启用：{self.enabled}\n"
            f"接收人：{self.owner_ids or '（未配置）'}\n"
            f"监听群：{sorted(self.watch_groups) or '（未配置）'}"
        )
