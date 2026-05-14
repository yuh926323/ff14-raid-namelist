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

設定 `.env`：

```bash
cp .env.example .env
nano .env
```

`.env` 至少要填：

```bash
DISCORD_BOT_TOKEN=你的-bot-token
DISCORD_CHANNEL_ID=你的頻道-id
```

建議也填 `DISCORD_GUILD_ID`，測試時 slash commands 通常會比較快出現。`.env` 已經被 `.gitignore` 排除，不會被提交。

### 用 Docker 啟動

此專案已在 `~/webserver/docker-compose.yml` 加入通用的 `python` service。Docker image 會從 `~/works/ff14-raid-namelist` build，並掛載整個 `~/works` 到 container 的 `/works`，不需要在 host 安裝 Python 套件。

從 `~/webserver` 啟動：

```bash
cd ~/webserver
docker compose build python
docker compose up -d python
```

查看 log：

```bash
docker compose logs -f python
```

進入 Python container：

```bash
docker compose exec python bash
```

進入後可以在 `/works` 看到你的所有專案：

```bash
cd /works/ff14-raid-namelist
python -m ff14_raid_namelist.bot
```

產生的資料會放在：

- `~/works/ff14-raid-namelist/data/bot-data.json`
- `~/works/ff14-raid-namelist/data/namelist.json`

可用的 slash commands：

- `/scan`：掃描被追蹤頻道的歷史訊息，並重建本機資料檔。
- `/summary`：顯示目前已解析與未解析的統計數字。
- `/export`：重新寫出產生的 JSON 名單。
- `/unparsed`：顯示最近無法解析的評價訊息。

Bot 執行期間，如果追蹤頻道中的評價訊息被新增、編輯或刪除，也會自動更新產生的 JSON。

## 離線匯出模式

如果只是要處理 DiscordChatExporter 匯出的 JSON，也可以直接用 Docker image 執行 CLI：

```bash
cd ~/webserver
docker compose run --rm \
  python \
  python -m ff14_raid_namelist \
  --input /works/ff14-raid-namelist/channel.json \
  --output /works/ff14-raid-namelist/namelist.json \
  --pretty
```

有安裝本機 Python 時，也可以直接執行：

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

Create `.env`:

```bash
cp .env.example .env
nano .env
```

At minimum, fill:

```bash
DISCORD_BOT_TOKEN=your-bot-token
DISCORD_CHANNEL_ID=your-channel-id
```

Setting `DISCORD_GUILD_ID` is also recommended while testing because slash commands usually appear faster in a single guild. `.env` is ignored by git.

### Run With Docker

This project is wired into `~/webserver/docker-compose.yml` as a generic `python` service. The Docker image is built from `~/works/ff14-raid-namelist` and mounts all of `~/works` into `/works`, so the host does not need Python package installation.

```bash
cd ~/webserver
docker compose build python
docker compose up -d python
```

View logs:

```bash
docker compose logs -f python
```

Enter the Python container:

```bash
docker compose exec python bash
```

Inside the container, all projects are available under `/works`:

```bash
cd /works/ff14-raid-namelist
python -m ff14_raid_namelist.bot
```

Generated data is written to:

- `~/works/ff14-raid-namelist/data/bot-data.json`
- `~/works/ff14-raid-namelist/data/namelist.json`

Available slash commands:

- `/scan` scans the tracked channel history and rebuilds the local data file.
- `/summary` shows current parsed/unparsed counts.
- `/export` rewrites the generated JSON output.
- `/unparsed` shows recently unparsed rating messages.

While running, the bot also updates the generated JSON whenever a tracked message is created, edited, or deleted.

## Offline Export Mode

To process DiscordChatExporter JSON with Docker:

```bash
cd ~/webserver
docker compose run --rm \
  python \
  python -m ff14_raid_namelist \
  --input /works/ff14-raid-namelist/channel.json \
  --output /works/ff14-raid-namelist/namelist.json \
  --pretty
```

If Python is installed locally, you can also run:

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
