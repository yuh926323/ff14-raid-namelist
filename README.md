# FF14 Raid Namelist

從 Discord 訊息中整理 FF14 玩家評價名單的小工具。

如果你會持續維護名單，建議使用 Discord bot 模式。Bot 會監看指定的 Discord 文字頻道，記錄含有 `✅` 或 `❌` 的訊息，並持續更新產生的 `namelist.json`。

## Discord Bot 模式

安裝 bot 需要的依賴：

```bash
python3 -m pip install -e '.[bot]'
```

到 Discord Developer Portal 建立一個 Discord application 和 bot，並在 bot 設定中啟用 **Message Content Intent**。接著邀請 bot 進入你的伺服器，並讓它在名單頻道擁有以下權限：

- View Channel
- Read Message History
- Send Messages
- Use Application Commands

設定必要環境變數：

```bash
export DISCORD_BOT_TOKEN='你的-bot-token'
export DISCORD_CHANNEL_ID='你的頻道-id'
```

可選環境變數：

```bash
export DISCORD_GUILD_ID='你的伺服器-id'
export NAMELIST_DATA_PATH='bot-data.json'
export NAMELIST_OUTPUT_PATH='namelist.json'
```

啟動 bot：

```bash
python3 -m ff14_raid_namelist.bot
```

可用的 slash commands：

- `/scan`：掃描被追蹤頻道的歷史訊息，並重建本機資料檔。
- `/summary`：顯示目前已解析與未解析的統計數字。
- `/export`：重新寫出產生的 JSON 名單。
- `/unparsed`：顯示最近無法解析的評價訊息。

Bot 執行期間，如果追蹤頻道中的評價訊息被新增、編輯或刪除，也會自動更新產生的 JSON。

## 離線匯出模式

```bash
python3 -m ff14_raid_namelist --input channel.json --output namelist.json --pretty
```

離線模式會讀取 DiscordChatExporter 匯出的 JSON。解析器只處理剛好包含一種評價符號的訊息行：

- `✅`：好的隊友
- `❌`：糟糕的隊友

支援常見的 FF14 角色名稱格式：

- `Firstname Lastname`
- `Firstname Lastname@World`
- `Firstname Lastname＠World`
- `Firstname Lastname (World)`

如果同一行同時包含 `✅` 和 `❌`，或是有評價符號但找不到安全的玩家名稱，該筆資料會被寫入 `unparsed[]`，方便之後人工檢查。

## 測試

```bash
python3 -m unittest discover -s tests
```

---

## English

Tools for summarizing FF14 player notes from Discord messages.

If you plan to maintain the list over time, bot mode is recommended. The bot watches one Discord text channel, records messages containing `✅` or `❌`, and keeps the generated `namelist.json` up to date.

## Bot Mode

Install the bot dependency:

```bash
python3 -m pip install -e '.[bot]'
```

Create a Discord application and bot in the Discord Developer Portal, then enable **Message Content Intent** for the bot. Invite the bot to your server with access to the namelist channel and these channel permissions:

- View Channel
- Read Message History
- Send Messages
- Use Application Commands

Set the required environment variables:

```bash
export DISCORD_BOT_TOKEN='your-bot-token'
export DISCORD_CHANNEL_ID='your-channel-id'
```

Optional environment variables:

```bash
export DISCORD_GUILD_ID='your-server-id'
export NAMELIST_DATA_PATH='bot-data.json'
export NAMELIST_OUTPUT_PATH='namelist.json'
```

Run the bot:

```bash
python3 -m ff14_raid_namelist.bot
```

Available slash commands:

- `/scan` scans the tracked channel history and rebuilds the local data file.
- `/summary` shows current parsed/unparsed counts.
- `/export` rewrites the generated JSON output.
- `/unparsed` shows recently unparsed rating messages.

While running, the bot also updates the generated JSON whenever a tracked message is created, edited, or deleted.

## Offline Export Mode

```bash
python3 -m ff14_raid_namelist --input channel.json --output namelist.json --pretty
```

Offline mode reads JSON exported by DiscordChatExporter. The parser only considers message lines containing exactly one rating marker:

- `✅` for a good teammate
- `❌` for a bad teammate

It recognizes common FF14 character formats:

- `Firstname Lastname`
- `Firstname Lastname@World`
- `Firstname Lastname＠World`
- `Firstname Lastname (World)`

Lines that contain both `✅` and `❌`, or contain a rating marker but no safe player name match, are written to `unparsed[]` for manual review.

## Tests

```bash
python3 -m unittest discover -s tests
```
