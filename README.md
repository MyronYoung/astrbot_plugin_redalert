# QQ 红包提醒

白名单群出现可领取的 QQ 红包时，**先私聊提醒主人，再在原群发一句感谢**。不领取、不调用 LLM，零 token 成本。

## 为什么做这个

QQ 红包的“领取”是 QQ 客户端原生动作（`nodeIKernelMsgService/grabRedBag`），并不是 OneBot 标准接口；很多 NapCat 版本没有把它暴露成 action。与其装闭源/来路不明的抢红包插件，不如先做一个安全、可控的“红包提醒”：

- 群里有人发红包 → 主人第一时间收到私聊
- 机器人不碰领取逻辑，不会因为自动抢红包被风控
- 不刷群、不调用模型，几乎零开销

## 功能

- 监听指定群的红包消息
- 只认 **`[QQ红包]` 固定文本** 或 **json/xml 红包卡片**，普通聊天提到“红包”不会误触发
- 已领完/已过期/来晚/口令红包默认不提醒；专属红包只在明确指向本机 QQ 时提醒
- 私聊通知主人，并在原群发一句带发送者名字的感谢
- 支持多个接收人
- 同一红包 10 秒内只提醒一次
- 优先 NapCat 私聊，失败自动回退 AstrBot 会话
- 自定义提醒模板
- `/红包测试`、`/红包状态` 管理命令

## 安装

1. 把插件目录放到 AstrBot 的 `data/plugins/astrbot_plugin_redalert/`
2. 重载/重启 AstrBot
3. 在 WebUI 插件配置里填写：
   - `owner_id` 或 `owner_ids`：接收提醒的 QQ
   - `watch_groups`：要监听的群号
4. 在群里发一个红包测试，或私聊机器人发 `/红包测试`

## 配置

| 配置 | 类型 | 说明 |
|---|---|---|
| `enabled` | bool | 是否启用 |
| `debug` | bool | 记录命中的红包卡片原文，便于适配不同客户端 |
| `bot_qq` | string | 机器人自己的 QQ，用于判断专属红包是否指向本机 |
| `allow_password_redpacket` | bool | 是否提醒口令红包，默认 false |
| `exclude_keywords` | list | 视为不可领取的关键词，默认已领完/已过期/手慢了/来晚了 |
| `owner_id` | string | 单个接收 QQ（兼容旧配置） |
| `owner_ids` | list | 多个接收 QQ，优先使用 |
| `watch_groups` | list | 监听的群号，留空不监听 |
| `group_thanks_enabled` | bool | 是否在原群发感谢 |
| `group_thanks_template` | text | 群感谢模板 |
| `notify_template` | text | 私聊模板，支持 `{group_name}`、`{group_id}`、`{sender_name}`、`{sender_id}`、`{time}` |

示例：

```json
{
  "enabled": true,
  "owner_ids": ["123456789"],
  "watch_groups": ["111111111", "222222222"],
  "notify_template": "💰 红包提醒\n群：{group_name}（{group_id}）\n发送者：{sender_name}（{sender_id}）\n时间：{time}\n快去抢！"
}
```

## 命令

| 命令 | 权限 | 作用 |
|---|---|---|
| `/红包测试` | 主人 | 给接收人发一条测试私聊 |
| `/红包状态` | 主人 | 查看启用状态、接收人、监听群 |


> 权限只按 `owner_id` / `owner_ids` 判断，与消息平台无关；非主人无法使用 `/红包测试`、`/红包状态`。



## NapCat 说明

NapCat 4.9.99 原生不会把 `walletElement` 转成 OneBot 段，真实红包会变成空消息。要使用本插件，需要协议端把 `walletElement` 作为 `json` 段上报（本机已验证的补丁方案）。

插件按红包 JSON 的真实字段判断：

- `receiver.content` 包含“红包”
- `grabState == 0`（未领）
- `grabbedAmount == "0"`
- `grapUin` 为空，或包含配置的 `bot_qq`

没有该补丁的 NapCat 不会触发提醒，也不会误报。

补丁脚本：

```bash
python tools/patch_napcat_wallet.py "D:\\AstrBot\\napcat\\napcat\\napcat.mjs"
```

脚本会先备份为 `napcat.mjs.bak-redalert`，重启 NapCat 后生效。

## 已知限制

- 本插件需要协议端把红包上报为 **`json` / `xml` 红包卡片**，或 `[QQ红包]` 文本。
- 部分 NapCat 版本会把真实红包上报成**空消息**（`message: []`、`raw_message: ""`），此时插件既无法识别、也不会误报。
- 不自动领取红包；自动领取需要协议端暴露 `grabRedBag` 能力，本项目不涉及。

## 兼容性

- AstrBot `>= 4.5.0`
- OneBot v11 / aiocqhttp / NapCat
- 不依赖第三方 Python 包

## 不做什么

- **不自动领取红包**：当前 NapCat 没有稳定的 `grabRedBag` OneBot action；自动领取需要改 QQ 客户端底层，风险高，本项目不做。
- **不刷屏**：只在检测到可领取红包时发一条感谢，其他时间不发言。
- **不调用 LLM**：不产生 token 费用。

## 隐私

插件只读取群消息中的红包标记和发送者/群号，用于私聊提醒；不保存聊天内容，不上传任何数据。

## License

MIT
