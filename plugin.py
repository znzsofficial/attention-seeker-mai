"""怕寂寞的麦麦 (LonelyMai) — 基于 Maisaka Planner 主动找话题。

不再自行构建 prompt 和调用 LLM，而是通过 maisaka.proactive.trigger()
将"冷场了，找话题聊聊"的意图注入 Planner 上下文，由 Maisaka 基于
人格、记忆、上下文和工具自行决定是否回复及如何表达。
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, time as datetime_time
from typing import Dict, Optional

from maibot_sdk import Command, MaiBotPlugin

from .config import LonelyMaiConfig


# ==================== 工具函数 ====================


def parse_time(time_str: str) -> datetime_time:
    hour, minute = map(int, time_str.split(":"))
    return datetime_time(hour, minute)


def is_in_time_range(current: datetime_time, start: datetime_time, end: datetime_time) -> bool:
    if start <= end:
        return start <= current <= end
    else:  # 跨夜
        return current >= start or current <= end


# ==================== 聊天流状态 ====================


class ChatStreamState:
    def __init__(self, stream_id: str, target_id: str):
        self.stream_id = stream_id
        self.target_id = target_id
        self.last_proactive_time: float = 0.0


# ==================== 插件主类 ====================


class LonelyMaiPlugin(MaiBotPlugin):
    config_model = LonelyMaiConfig

    def __init__(self):
        super().__init__()
        self._states: Dict[str, ChatStreamState] = {}
        self._scheduler_task: Optional[asyncio.Task] = None
        self._bot_qq: str = ""

    # ========== 生命周期 ==========

    async def on_load(self) -> None:
        if not self.config.plugin.enabled:
            self.ctx.logger.info("LonelyMai 已禁用")
            return

        # 防止重复启动
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None

        self._bot_qq = await self._get_global_str("bot.qq_account", "")

        self._scheduler_task = asyncio.create_task(self._schedule_loop())
        self.ctx.logger.info("LonelyMai 调度器已启动")

    async def on_unload(self) -> None:
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        self.ctx.logger.info("LonelyMai 已卸载")

    async def on_config_update(self, *args, **kwargs):
        del args, kwargs
        await self._init_target_streams()

    async def _get_global_str(self, key: str, default: str = "") -> str:
        try:
            val = await self.ctx.config.get(key, default)
        except Exception as e:
            self.ctx.logger.warning(f"读取全局配置 {key} 失败: {e}")
            return default
        if isinstance(val, dict):
            val = val.get("value", default)
        return str(val or default)

    async def _init_target_streams(self) -> None:
        previous = {target_id: state.last_proactive_time for target_id, state in self._states.items()}
        resolved: Dict[str, ChatStreamState] = {}

        for group_qq in self.config.target.allowed_groups:
            target_id = str(group_qq).strip()
            if not target_id:
                continue
            sid = await self._resolve_session_id(target_id, True)
            if sid:
                state = ChatStreamState(sid, target_id)
                state.last_proactive_time = previous.get(target_id, 0.0)
                resolved[target_id] = state
            else:
                self.ctx.logger.warning(f"无法解析群聊: {target_id}")

        for user_qq in self.config.target.allowed_friends:
            target_id = str(user_qq).strip()
            if not target_id:
                continue
            sid = await self._resolve_session_id(target_id, False)
            if sid:
                state = ChatStreamState(sid, target_id)
                state.last_proactive_time = previous.get(target_id, 0.0)
                resolved[target_id] = state
            else:
                self.ctx.logger.warning(f"无法解析私聊: {target_id}")

        changed = set(resolved) != set(self._states)
        self._states = resolved
        if changed or not resolved:
            self.ctx.logger.info(f"共注册 {len(self._states)} 个目标流")

    async def _resolve_session_id(self, qq: str, is_group: bool) -> Optional[str]:
        try:
            if is_group:
                result = await self.ctx.chat.get_stream_by_group_id(qq)
            else:
                result = await self.ctx.chat.get_stream_by_user_id(qq)
        except Exception as e:
            self.ctx.logger.error(f"ctx.chat 查询失败 ({qq}): {e}")
            return None

        if not isinstance(result, dict):
            self.ctx.logger.warning(f"会话查询返回了非字典 ({qq}): {type(result).__name__}")
            return None
        if result.get("success") is False:
            self.ctx.logger.warning(f"会话查询失败 ({qq}): {result.get('error') or result}")
            return None
        stream = result.get("stream", result if "session_id" in result else None)
        if not stream:
            return None
        if isinstance(stream, dict):
            return stream.get("session_id") or stream.get("stream_id")
        return getattr(stream, "session_id", None) or getattr(stream, "stream_id", None)

    # ========== 调度循环 ==========

    def _next_sleep_seconds(self) -> int:
        base_interval = max(1, self.config.scheduler.check_interval)
        jitter = self.config.scheduler.jitter
        actual_minutes = base_interval + random.randint(-jitter, jitter) if jitter > 0 else base_interval
        return max(60, actual_minutes * 60)

    async def _schedule_loop(self) -> None:
        while True:
            try:
                if not self.config.plugin.enabled or not self.config.scheduler.enabled:
                    await asyncio.sleep(60)
                    continue

                await self._init_target_streams()
                if not self._states:
                    self.ctx.logger.warning("没有可用目标流，15 秒后重新解析")
                    await asyncio.sleep(15)
                    continue

                for target_id, state in list(self._states.items()):
                    if (target_id not in self.config.target.allowed_groups and
                        target_id not in self.config.target.allowed_friends):
                        continue

                    try:
                        await self._check_and_trigger(state, target_id)
                    except Exception as e:
                        self.ctx.logger.error(f"[{target_id}] 检查异常: {e}", exc_info=True)

                sleep_seconds = self._next_sleep_seconds()
                if self.config.log.scheduler_log:
                    self.ctx.logger.info(f"[调度器] 下次检查: +{sleep_seconds // 60}min")
                await asyncio.sleep(sleep_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.ctx.logger.error(f"调度器异常: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _check_and_trigger(self, state: ChatStreamState, target_id: str) -> None:
        cfg = self.config
        now = datetime.now()
        current_time = now.time()
        start = parse_time(cfg.scheduler.start_time)
        end = parse_time(cfg.scheduler.end_time)

        if not is_in_time_range(current_time, start, end):
            self._skip(target_id, f"不在 {cfg.scheduler.start_time}-{cfg.scheduler.end_time}")
            return

        min_interval = cfg.scheduler.min_interval_between_chats * 60
        if state.last_proactive_time and (now.timestamp() - state.last_proactive_time) < min_interval:
            remain = int(min_interval - (now.timestamp() - state.last_proactive_time))
            self._skip(target_id, f"距上次主动还有 {remain} 秒")
            return

        isolation_seconds = cfg.scheduler.isolation_time * 60
        if isolation_seconds > 0:
            last_msg_time = await self._get_last_msg_time(state.stream_id)
            if last_msg_time is not None and (now.timestamp() - last_msg_time) < isolation_seconds:
                self._skip(target_id, "隔离期未到")
                return

        if random.random() >= cfg.scheduler.probability:
            self._skip(target_id, f"概率未命中 ({cfg.scheduler.probability})")
            return

        self.ctx.logger.info(f"[{target_id}] 触发主动聊天")
        if await self._do_proactive_chat(state, target_id):
            state.last_proactive_time = now.timestamp()

    # ========== 消息时间查询 ==========

    async def _get_last_msg_time(self, session_id: str) -> Optional[float]:
        """获取最近一条非 bot 消息的时间戳。"""
        try:
            end_ts = time.time()
            start_ts = end_ts - 3600 * 24 * 7
            raw = await self.ctx.message.get_by_time_in_chat(
                session_id,
                start_time=str(start_ts),
                end_time=str(end_ts),
                limit=5,
                limit_mode="latest",
            )
            if not isinstance(raw, list):
                return None

            for msg in raw:
                if not isinstance(msg, dict):
                    continue
                sender_id = self._get_msg_user_id(msg)
                if self._bot_qq and sender_id == self._bot_qq:
                    continue
                ts = msg.get("timestamp", 0)
                try:
                    return float(ts)
                except (TypeError, ValueError):
                    pass
            return None
        except Exception:
            return None

    # ========== 主动聊天核心 ==========

    async def _do_proactive_chat(self, state: ChatStreamState, target_id: str) -> bool:
        """通过 Maisaka 主动触发 API 非显式注入意图到 Planner 上下文。

        意图文本从 config.intent.text 读取，用户可自定义。
        """
        try:
            await self.ctx.maisaka.proactive.trigger(
                stream_id=state.stream_id,
                intent=self.config.intent.text,
                reason=self.config.intent.reason,
                metadata={
                    "source": "lonelymai",
                    "target_id": target_id,
                },
            )
            self.ctx.logger.info(f"[{target_id}] 已注入 Planner 上下文")
            return True
        except Exception as e:
            self.ctx.logger.error(f"[{target_id}] 主动触发失败: {e}", exc_info=True)
            return False

    def _skip(self, target_id: str, reason: str) -> None:
        if self.config.log.scheduler_log:
            self.ctx.logger.info(f"[{target_id}] 跳过: {reason}")

    @staticmethod
    def _get_msg_user_id(msg: dict) -> str:
        info = msg.get("message_info") or {}
        user = info.get("user_info") or {}
        return str(user.get("user_id", "") or "")

    # ========== 手动命令 ==========

    @Command("lonelymai_trigger", description="手动触发一次主动发言", pattern=r"^/saymai$")
    async def cmd_trigger(self, stream_id: str = "", **kwargs):
        if not stream_id:
            return False, "无法获取当前会话 ID", True

        target = None
        for tid, st in self._states.items():
            if st.stream_id == stream_id:
                target = tid
                break
        if not target:
            return False, "当前会话未在白名单中", True

        success = await self._do_proactive_chat(self._states[target], target)
        if success:
            return True, "已触发主动发言", True
        else:
            return False, "主动发言失败", True


def create_plugin():
    return LonelyMaiPlugin()
