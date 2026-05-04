# Dracula Daily Discord Bot

A Discord bot that checks [Dracula Daily](https://draculadaily.substack.com/) once a day and posts a rich embed to a channel whenever a new entry is published.

## How It Works

- At **08:00 UTC** each day, the bot fetches the Substack RSS feed.
- If the latest post is new (not seen before), it sends a Discord embed with the title, excerpt, date, and a link to the full post.
- The last seen post is tracked in `state.json` so nothing is sent twice.

---

## Setup

### 1. Create a Discord Bot

1. Go to [https://discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application**, give it a name (e.g. `Dracula Daily`).
3. Go to **Bot** → click **Add Bot**.
4. Under **Token**, click **Reset Token** and copy it — this is your `DISCORD_TOKEN`.
5. Under **Privileged Gateway Intents**, no extra intents are needed.

### 2. Invite the Bot to Your Server

1. Go to **OAuth2 → URL Generator**.
2. Under **Scopes**, select `bot`.
3. Under **Bot Permissions**, select `Send Messages` and `Embed Links`.
4. Copy the generated URL, open it in your browser, and invite the bot to your server.

### 3. Get the Channel ID

1. In Discord, go to **User Settings → Advanced** and enable **Developer Mode**.
2. Right-click the target channel and select **Copy Channel ID**.
3. This is your `CHANNEL_ID`.

### 4. Local Setup

```bash
# Clone the repo
git clone <your-repo-url>
cd dracula-daily

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and fill in DISCORD_TOKEN and CHANNEL_ID

# Run the bot
python bot.py
```

The bot will start and wait until 08:00 UTC to check the feed. To test it immediately, you can temporarily change `CHECK_TIME` in `bot.py` to a time a minute or two from now.

---

## Deploy to Railway (Free)

[Railway](https://railway.app) offers a free tier suitable for lightweight bots.

1. Push your code to a GitHub repository.
   > **Important:** Make sure `.env` is in `.gitignore` so your token is never committed.

2. Go to [railway.app](https://railway.app) and sign in with GitHub.

3. Click **New Project → Deploy from GitHub repo** and select your repository.

4. Once deployed, go to your service → **Variables** and add:
   - `DISCORD_TOKEN` — your bot token
   - `CHANNEL_ID` — your channel ID

5. Railway will automatically detect the `Procfile` and run `python bot.py` as a worker process.

> `state.json` is stored on the Railway filesystem. Note that Railway's free tier may restart containers periodically; the state file will reset on a full redeploy. For persistent state across redeploys, consider storing the last GUID in a Railway-provided PostgreSQL or Redis add-on, or an environment variable updated via the Railway API.

---

## Files

| File | Description |
|------|-------------|
| `bot.py` | Main bot — task loop, embed builder, Discord client |
| `config.py` | Loads and validates environment variables |
| `state.json` | Persists the last seen post GUID |
| `.env.example` | Template for required environment variables |
| `requirements.txt` | Python dependencies |
| `Procfile` | Railway/Heroku process definition |
# dracula-daily-bot
