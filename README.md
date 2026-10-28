# QQ 红包提醒

白名单群出现 QQ 红包时，**只私聊提醒主人**。不领取、不在群里发言、不调用 LLM，零 token 成本。

## 为什么做这个

QQ 红包的“领取”是 QQ 客户端原生动作（`nodeIKernelMsgService/grabRedBag`），并不是 OneBot 标准接口；很多 NapCat 版本没有把它暴露成 action。与其装闭源/来路不明的抢红包插件，不如先做一个安全、可控的“红包提醒”：

- 群里有人发红包 → 主人第一时间收到私聊
- 机器人不碰领取逻辑，不会因为自动抢红包被风控
- 不刷群、不调用模型，几乎零开销

## 功能

- 监听指定群的红包消息
- 只私聊通知主人，不在群里发消息
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
| `owner_id` | string | 单个接收 QQ（兼容旧配置） |
| `owner_ids` | list | 多个接收 QQ，优先使用 |
| `watch_groups` | list | 监听的群号，留空不监听 |
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

## 兼容性

- AstrBot `>= 4.5.0`
- OneBot v11 / aiocqhttp / NapCat
- 不依赖第三方 Python 包

## 不做什么

- **不自动领取红包**：当前 NapCat 没有稳定的 `grabRedBag` OneBot action；自动领取需要改 QQ 客户端底层，风险高，本项目不做。
- **不在群里发言**：避免刷屏和暴露提醒逻辑。
- **不调用 LLM**：不产生 token 费用。

## 隐私

插件只读取群消息中的红包标记和发送者/群号，用于私聊提醒；不保存聊天内容，不上传任何数据。

## License

MIT
