"""QQ 红包提醒：白名单群出现红包时，只私聊主人。

设计目标：
- 不领取、不在群里发言、不调用 LLM，零 token；
- 只监听配置里的群；
- 兼容 aiocqhttp/OneBot v11，优先用 NapCat 私聊，失败回退 AstrBot 会话；
- 同一红包 10 秒内只提醒一次。
"""

from __future__ import annotations

import json
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
        owners = self.conf.get("owner_ids") or []
        if not owners and self.conf.get("owner_id"):
            owners = [self.conf.get("owner_id")]
        self.owner_ids = [str(x).strip() for x in owners if str(x).strip()]
        groups = self.conf.get("watch_groups") or []
        self.watch_groups = {str(g).strip() for g in groups if str(g).strip()}
        self.template = str(self.conf.get("notify_template") or DEFAULT_TEMPLATE).replace("\\n", "\n")
        self.seen: dict[str, float] = {}
        if not self.owner_ids:
            logger.warning("[redalert] 未配置 owner_id / owner_ids，红包提醒不会发送")
        if not self.watch_groups:
            logger.warning("[redalert] watch_groups 为空，不会监听任何群")

    def _is_owner(self, event) -> bool:
        try:
            if str(event.get_sender_id()) in self.owner_ids:
                return True
            pn = (event.get_platform_name() or "").lower()
            return "aiocqhttp" not in pn and "qq" not in pn
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

    def _is_red_packet(self, event, msg: str) -> bool:
        if "QQ红包" in msg:
            return True
        # 有些客户端的红包是 json/xml 卡片，文本里不一定带 QQ红包
        for seg in self._raw_segments(event):
            try:
                data = seg.get("data", {}) if isinstance(seg, dict) else {}
                blob = json.dumps(data, ensure_ascii=False).lower()
                if any(k in blob for k in ("redpacket", "redbag", "红包")):
                    return True
            except Exception:
                continue
        try:
            for comp in event.get_messages():
                d = comp.toDict() if hasattr(comp, "toDict") else {}
                if d.get("type") in ("json", "xml"):
                    blob = json.dumps(d, ensure_ascii=False).lower()
                    if any(k in blob for k in ("redpacket", "redbag", "红包")):
                        return True
        except Exception:
            pass
        return False

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
            if not self._is_red_packet(event, msg):
                return
            gid = str(event.get_group_id() or "")
            if gid not in self.watch_groups:
                return
            sender = str(event.get_sender_id() or "")
            if sender == str(event.get_self_id() or ""):
                return

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
