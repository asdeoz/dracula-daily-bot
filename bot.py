import json
import re
import datetime
import logging
from pathlib import Path

import discord
import feedparser
from discord import app_commands
from discord.ext import tasks

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

STATE_FILE = Path("state.json")
DRACULA_RED = 0x8B0000
DRACULA_LOGO = (
    "https://substackcdn.com/image/fetch/w_256,c_limit,f_auto,q_auto:best,"
    "fl_progressive:steep/https%3A%2F%2Fbucketeer-e05bbc84-baa3-437e-9518-"
    "adb32be77984.s3.amazonaws.com%2Fpublic%2Fimages%2F"
    "1e5f0bc0-4f05-41e8-8c7a-e11058e3ae25_1280x1280.png"
)


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        with STATE_FILE.open() as f:
            return json.load(f)
    return {"last_seen_guid": None, "channel_id": None, "check_hour": config.CHECK_HOUR_UTC}


def save_state(state: dict) -> None:
    with STATE_FILE.open("w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Feed helpers
# ---------------------------------------------------------------------------

def fetch_latest_entry() -> feedparser.FeedParserDict | None:
    feed = feedparser.parse(config.FEED_URL)
    if feed.bozo:
        log.warning("Feed parse warning: %s", feed.bozo_exception)
    if not feed.entries:
        log.warning("No entries found in feed.")
        return None
    return feed.entries[0]


def build_embed(entry: feedparser.FeedParserDict) -> discord.Embed:
    title = entry.get("title", "New Dracula Daily Post")
    link = entry.get("link", "https://draculadaily.substack.com")

    summary_html = entry.get("summary", "")
    clean = re.sub(r"<[^>]+>", "", summary_html)
    clean = re.sub(r"\s+", " ", clean).strip()
    description = clean[:300] + ("…" if len(clean) > 300 else "")

    published_parsed = entry.get("published_parsed")
    if published_parsed:
        pub_date = datetime.datetime(*published_parsed[:6], tzinfo=datetime.timezone.utc)
    else:
        pub_date = datetime.datetime.now(datetime.timezone.utc)

    embed = discord.Embed(
        title=title,
        url=link,
        description=description or "*No preview available.*",
        color=DRACULA_RED,
        timestamp=pub_date,
    )
    embed.set_thumbnail(url=DRACULA_LOGO)
    embed.set_footer(text="Dracula Daily • draculadaily.substack.com")

    return embed


def restart_loop(hour: int) -> None:
    """Restart the check_feed loop with a new check time."""
    if check_feed.is_running():
        check_feed.cancel()
    new_time = datetime.time(hour=hour, minute=0, tzinfo=datetime.timezone.utc)
    check_feed._time = [new_time]  # mutate the internal time list used by the loop
    check_feed.start()
    log.info("Feed check rescheduled to %02d:00 UTC.", hour)


# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@tree.command(name="dracula-help", description="Show information and setup instructions for Dracula Daily.")
async def dracula_help(interaction: discord.Interaction) -> None:
    state = load_state()
    channel_id = state.get("channel_id")
    check_hour = state.get("check_hour", config.CHECK_HOUR_UTC)
    channel_status = f"<#{channel_id}>" if channel_id else "not set — use `/dracula-setchannel` to configure it"

    embed = discord.Embed(
        title="Dracula Daily Bot",
        description=(
            "This bot checks [Dracula Daily](https://draculadaily.substack.com/) "
            "once a day and posts new entries to a channel of your choice."
        ),
        color=DRACULA_RED,
    )
    embed.set_thumbnail(url=DRACULA_LOGO)
    embed.add_field(name="Posting channel", value=channel_status, inline=False)
    embed.add_field(
        name="Commands",
        value=(
            "`/dracula-setchannel` — Set the current channel as the posting channel *(requires Manage Channels)*\n"
            "`/dracula-time <0-23>` — Set the hour (UTC) the bot checks for new posts *(requires Manage Channels)*\n"
            "`/dracula-help` — Show this message"
        ),
        inline=False,
    )
    embed.add_field(name="Check time", value=f"Daily at {check_hour:02d}:00 UTC", inline=False)
    embed.set_footer(text="Only visible to you")

    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="dracula-setchannel", description="Set this channel as the Dracula Daily posting channel.")
@app_commands.checks.has_permissions(manage_channels=True)
async def setchannel(interaction: discord.Interaction) -> None:
    state = load_state()
    state["channel_id"] = interaction.channel_id
    save_state(state)
    log.info("Channel set to %s by %s.", interaction.channel_id, interaction.user)
    await interaction.response.send_message(
        f"Done! Dracula Daily posts will be sent to <#{interaction.channel_id}>.",
        ephemeral=True,
    )


@setchannel.error
async def setchannel_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You need the **Manage Channels** permission to use this command.",
            ephemeral=True,
        )


@tree.command(name="dracula-time", description="Set the hour (UTC) the bot checks for new posts. Accepts 0-23.")
@app_commands.describe(hour="Hour in UTC (0-23), e.g. 8 for 08:00 UTC")
@app_commands.checks.has_permissions(manage_channels=True)
async def set_check_time(interaction: discord.Interaction, hour: int) -> None:
    if hour < 0 or hour > 23:
        await interaction.response.send_message(
            "Invalid time. Please provide an integer between **0** and **23** (e.g. `/dracula-time 8` for 08:00 UTC).",
            ephemeral=True,
        )
        return

    state = load_state()
    state["check_hour"] = hour
    save_state(state)
    restart_loop(hour)

    await interaction.response.send_message(
        f"Done! The bot will now check for new posts daily at **{hour:02d}:00 UTC**.",
        ephemeral=True,
    )


@set_check_time.error
async def set_check_time_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You need the **Manage Channels** permission to use this command.",
            ephemeral=True,
        )
    elif isinstance(error, app_commands.TransformerError):
        await interaction.response.send_message(
            "Invalid value. Please provide an integer between **0** and **23** (e.g. `/dracula-time 8`).",
            ephemeral=True,
        )


@tasks.loop(
    time=datetime.time(hour=config.CHECK_HOUR_UTC, minute=0, tzinfo=datetime.timezone.utc)
)
async def check_feed() -> None:
    log.info("Checking Dracula Daily feed...")
    state = load_state()

    channel_id = state.get("channel_id")
    if not channel_id:
        log.warning("No channel set. Use /dracula-setchannel in your server first.")
        return

    entry = fetch_latest_entry()
    if entry is None:
        return

    guid = entry.get("id") or entry.get("link")
    if guid == state.get("last_seen_guid"):
        log.info("No new post found. Last seen: %s", guid)
        return

    log.info("New post found: %s", guid)

    try:
        channel = await client.fetch_channel(channel_id)
    except discord.NotFound:
        log.error("Channel %s not found. Run /dracula-setchannel again.", channel_id)
        return
    except discord.Forbidden:
        log.error("Bot lacks permission to access channel %s.", channel_id)
        return

    embed = build_embed(entry)
    await channel.send(embed=embed)
    log.info("Embed sent to channel %s.", channel_id)

    state["last_seen_guid"] = guid
    save_state(state)


@check_feed.before_loop
async def before_check_feed() -> None:
    await client.wait_until_ready()


@client.event
async def on_ready() -> None:
    log.info("Logged in as %s (ID: %s)", client.user, client.user.id)
    synced = await tree.sync()
    log.info("Slash commands synced: %s", [cmd.name for cmd in synced])

    # Restore saved check time if it differs from the default
    state = load_state()
    saved_hour = state.get("check_hour", config.CHECK_HOUR_UTC)
    if saved_hour != config.CHECK_HOUR_UTC:
        restart_loop(saved_hour)
    elif not check_feed.is_running():
        check_feed.start()

    log.info("Daily check scheduled at %02d:00 UTC.", saved_hour)
    await check_feed()  # Run immediately on startup


if __name__ == "__main__":
    client.run(config.DISCORD_TOKEN)
