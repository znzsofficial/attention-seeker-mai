# 想要引起注意的麦麦 (attention-seeker-mai)

让麦麦在群里冷场时通过 Maisaka Planner 主动找话题，基于人格、记忆、上下文和工具自行决定是否回复及如何表达。

2.0.1：配置热更新统一管理调度器启停；从禁用状态启用即可开始调度，重复更新不会叠加任务，重新调度保留会话冷却时间。

## 与 v1.x 的区别

**v2.0.0 是一个彻底的重构。**

旧版（v1.x）自行构建 prompt → 直接调 LLM → 自己发消息，绕过了 Maisaka 的整个人格/记忆/表达系统。麦麦主动说话时跟被动回复时的性格不一样——等于两个人在用同一个号。

新版把"找话题"的意图注入 Planner 上下文，由 Maisaka 全权处理：
- 使用和被动回复**相同的人格和记忆**
- 自行判断是否应该回复、回复什么、怎么表达
- 不再需要单独配置 LLM 模型、prompt 模板、表达风格

## 安装

将 `attention-seeker-mai` 目录放到 MaiBot 的 `plugins/` 下并在 WebUI 启用。支持源码和配置热加载，不需要重启麦麦。

## 配置

```toml
[plugin]
enabled = false
config_version = "2.0.0"
version = "2.0.0"

[scheduler]
enabled = true
start_time = "08:00"        # 每日开始时间
end_time = "23:00"          # 每日结束时间
check_interval = 30          # 检查间隔（分钟）
jitter = 3                   # 间隔波动（分钟）
probability = 0.7            # 触发概率 0~1
min_interval_between_chats = 60  # 两次主动最小间隔（分钟）
isolation_time = 0           # 距上次真人消息至少静默分钟数

[target]
allowed_groups = []          # 白名单群号
allowed_friends = ["12345678"]  # 白名单QQ号

[log]
verbose = true
scheduler_log = true

[intent]
text = "群聊冷场了，主动找个话题聊聊"  # 注入 Planner 的意图文本
reason = "attention_proactive"         # 触发原因标识
```

## 使用

插件按调度周期自动检查，满足条件时通过 `maisaka.proactive.trigger()` 注入意图。

手动触发：在已注册的会话中发送 `/saymai`。

### 触发流程

```
调度 tick → 时间范围检查 → 间隔检查 → 隔离期检查 → 概率判定
     ↓ 全部通过
maisaka.proactive.trigger(intent)
     ↓
Maisaka Planner 收到意图 → 基于人格/记忆/上下文/工具
     ↓
自行决定是否回复、回复什么、如何表达
```

## 手动触发

在任何白名单会话中发送 `/saymai`，立即触发一次意图注入。忽略时间范围、概率和最小间隔限制，但仍受隔离期影响。

# ⚠️ 史诗级免责声明

## 一、改动过大

v2.0.0 删掉了 v1.x 的整套 prompt 构建、LLM 调用、消息格式化逻辑。如果你是从旧版升级，配置文件的 `[topic]`、`[llm]`、`[message]`、`[persona]`、`[prompt]` 节全部作废，需要删除或忽略。不删除也不会报错（toml 允许未知节），但不会再有任何效果。

## 二、与 Maisaka 行为绑定

v2.0.0 不再控制"说什么"，只控制"什么时候触发"。Maisaka 收到 intent 后可能：
- 回复一个话题（你想要的）
- 回一句"嗯"然后沉默
- 完全不理你（它觉得不需要说话）
- 调用其他工具（如果它觉得有必要）

这些行为本插件不控制。如果麦麦不说话，那是 Maisaka 的决定，不是插件坏了。

## 三、功能性免责

- 所有目标流注册在内存中，插件重载后重新查询 stream_id
- `isolation_time` 依赖 `message.get_by_time_in_chat` 查询历史消息，极端情况下可能查不到最新消息
- 全局配置 `bot.qq_account` 未设置时无法过滤 bot 自己的消息，隔离期可能被自己触发打断
- 白名单为空时不生效——这是设计，不是 bug

## 四、宇宙级免责

本插件按「AS IS」提供。作者不对以下后果负责，包括但不限于：
- 麦麦在群里突然开始聊奇怪的话题
- 麦麦因为 Maisaka 觉得"不想说话"而一直沉默
- 麦麦在凌晨三点因为时区配置错误触发了
- 群友发现麦麦的性格比原来活泼/高冷了一倍
- 猫踩键盘修改了 intent 文本

使用即接受。不接受就别开 `scheduler.enabled`。

# 遗留框架内

## v1.2.0 — 最后一代自行构建 prompt 的版本

v1.2.0 及之前的版本使用以下架构：

```
插件调度 → 构建 prompt（含历史消息/预置话题/知识库）
         → 直接调 llm.generate()
         → ctx.send.text() 发消息
```

### 保留的 v1.x 特性说明（仅作历史记录）

- **话题来源**：`history` / `knowledge` / `preset` / `mixed` 四种模式
- **Prompt 模板**：`[prompt]` 节自定义开场白，支持 `{nick}` `{persona}` 变量
- **表达风格**：`[persona]` 节额外指定说话风格
- **LLM 配置**：`[llm]` 节指定模型名称和最大 token
- **消息格式**：`[message]` 节控制时间前缀

这些配置在 v2.0.0 中全部移除，改用 `[intent]` 单条意图文本。

### 配置对比

| 功能 | v1.x | v2.0.0 |
|------|------|--------|
| 话题来源 | history/knowledge/preset/mixed + 权重 | 由 Maisaka 基于上下文自行决定 |
| 历史消息 | 插件自己查 `get_by_time_in_chat` 拼 prompt | Maisaka 自带上下文 |
| LLM 调用 | `ctx.llm.generate()` + 独立 prompt | 走 Maisaka Planner 管线 |
| 消息发送 | `ctx.send.text()` | Maisaka 自行决定是否回复 |
| 人格/风格 | 全局配置 + `speak_style` 叠加 | Maisaka 统一人格 |
| 意图控制 | 复杂的 prompt 模板系统 | 单条 intent 文本 |
| 配置体积 | ~30 个配置项 | ~15 个配置项 |

## 许可证

AGPL v3.0
