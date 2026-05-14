# FF14 Raid Namelist

從 Discord 訊息中整理 FF14 玩家評價名單的小工具。

如果你會持續維護名單，建議使用 Discord bot 模式。Bot 會監看指定的 Discord 文字頻道，記錄含有 `✅` 或 `❌` 的訊息，並持續更新產生的 `namelist.json`。

## Discord Bot 模式

### 從零開始設定

1. 到 Discord Developer Portal 建立 application：
   - 開啟 <https://discord.com/developers/applications>
   - 按 **New Application**
   - 輸入名稱，例如 `FF14 Raid Namelist`

2. 建立 bot 並取得 token：
   - 進入 application 後，打開 **Bot** 頁面
   - 建立 bot
   - 按 **Reset Token** 或 **Copy Token**
   - 不要把 token 貼到 Discord、GitHub 或任何聊天中

3. 啟用 bot 讀訊息內容的權限：
   - 在 **Bot** 頁面找到 **Privileged Gateway Intents**
   - 開啟 **Message Content Intent**
   - 儲存設定

4. 產生邀請連結：
   - 打開 **OAuth2** -> **URL Generator**
   - Scopes 勾選 `bot` 和 `applications.commands`
   - Bot Permissions 勾選：
     - View Channel
     - Read Message History
     - Send Messages
     - Use Application Commands
   - 複製產生出的 URL，開啟後把 bot 加進你的 Discord server

5. 取得 Discord ID：
   - Discord 使用者設定中啟用 **Developer Mode**
   - 右鍵名單頻道，複製 **Channel ID**
   - 右鍵伺服器圖示，複製 **Server ID**，這是可選的，但測試 slash command 時建議設定

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

也可以複製 `.env.example` 成 `.env` 自己留著記錄設定值；`.env` 已經被 `.gitignore` 排除，不會被提交。

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

### Setup From Scratch

1. Create an application in the Discord Developer Portal:
   - Open <https://discord.com/developers/applications>
   - Click **New Application**
   - Enter a name, such as `FF14 Raid Namelist`

2. Create the bot and get its token:
   - Open the **Bot** page for the application
   - Create a bot
   - Click **Reset Token** or **Copy Token**
   - Do not paste the token into Discord, GitHub, or chat

3. Enable message content access:
   - On the **Bot** page, find **Privileged Gateway Intents**
   - Enable **Message Content Intent**
   - Save changes

4. Generate the invite URL:
   - Open **OAuth2** -> **URL Generator**
   - Select the `bot` and `applications.commands` scopes
   - Select these Bot Permissions:
     - View Channel
     - Read Message History
     - Send Messages
     - Use Application Commands
   - Open the generated URL and invite the bot to your Discord server

5. Copy Discord IDs:
   - Enable **Developer Mode** in Discord user settings
   - Right-click the namelist channel and copy **Channel ID**
   - Right-click the server icon and copy **Server ID**; this is optional, but recommended while testing slash commands

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
