"""LonelyMai 插件配置模型。"""

from __future__ import annotations

from typing import List

from maibot_sdk import Field, PluginConfigBase


DAILY_LIFE_INTENT = (
    "你想主动分享一点自己的生活，而不是提醒对方回消息。"
    "结合当前人格、长期记忆、时间和最近对话，选一个与你自己有关的小话题："
    "此刻的感受、兴趣里的小发现、正在想的事情、想尝试的小计划，或已经建立的日常生活线索。"
    "像忽然想跟熟悉的人说起的一两句话，自然亲近，不写汇报、流水账或话题清单。"
    "不要复述这段意图，不说冷场了；不要催回复，也不要惯性追问在干嘛、吃了吗或怎么不理我。"
    "尽量不重复最近已经主动说过的内容，不替对方编造经历或安排活动。"
    "日常表达要符合已有的人格与生活设定，不额外创建职业、地点或重大经历；"
    "没有依据时聊感受、兴趣和愿望，不把未发生的线下事件或未执行的查询、发帖、下单等外部操作说成已经完成。"
    "若对方正忙、话题正在进行或时机不合适，可以暂时不发；有话想分享时直接分享，不必以问题收尾。"
)


class PluginSection(PluginConfigBase):
    enabled: bool = Field(default=True, description="是否启用插件")
    config_version: str = Field(default="2.0.0", description="配置文件版本号")
    version: str = Field(default="2.0.2", description="插件版本")


class SchedulerSection(PluginConfigBase):
    """调度器设置——控制何时、多久触发一次主动注入。"""
    enabled: bool = Field(default=True, description="是否开启主动聊天")
    start_time: str = Field(default="08:00", description="每日开始时间 (HH:MM)")
    end_time: str = Field(default="23:00", description="每日结束时间 (HH:MM)")
    check_interval: int = Field(default=30, description="检查间隔（分钟）")
    jitter: int = Field(default=5, description="间隔波动（分钟）")
    probability: float = Field(default=0.2, description="触发概率 0~1")
    min_interval_between_chats: int = Field(default=60, description="两次主动聊天最小间隔（分钟）")
    isolation_time: int = Field(default=15, description="距上次真人消息至少静默多少分钟才触发")


class TargetSection(PluginConfigBase):
    """白名单——只对指定的群/用户生效。"""
    allowed_groups: List[str] = Field(default_factory=list, description="白名单群号列表")
    allowed_friends: List[str] = Field(default_factory=list, description="白名单QQ号列表")


class LogSection(PluginConfigBase):
    verbose: bool = Field(default=True)
    scheduler_log: bool = Field(default=True)


class IntentSection(PluginConfigBase):
    """主动触发时注入 Planner 的意图描述。"""
    text: str = Field(
        default=DAILY_LIFE_INTENT,
        description="发送给 Planner 的主动发言意图，默认分享自己的日常、感受、兴趣和计划，可自定义"
    )
    reason: str = Field(
        default="attention_proactive",
        description="触发原因标识，用于日志和去重"
    )


class LonelyMaiConfig(PluginConfigBase):
    plugin: PluginSection = Field(default_factory=PluginSection)
    scheduler: SchedulerSection = Field(default_factory=SchedulerSection)
    target: TargetSection = Field(default_factory=TargetSection)
    log: LogSection = Field(default_factory=LogSection)
    intent: IntentSection = Field(default_factory=IntentSection)
