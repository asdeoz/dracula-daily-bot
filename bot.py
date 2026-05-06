import json
import re
import datetime
import logging
from pathlib import Path
from typing import Optional

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
    return {"channels": {}}


def save_state(state: dict) -> None:
    with STATE_FILE.open("w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Feed helpers
# ---------------------------------------------------------------------------

def fetch_latest_entry() -> Optional[feedparser.FeedParserDict]:
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





# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@tree.command(name="dracula-help", description="Show information and setup instructions for Dracula Daily.")
async def dracula_help(interaction: discord.Interaction) -> None:
    state = load_state()
    guild_id = str(interaction.guild_id)
    channel_config = state.get("channels", {}).get(guild_id)
    channel_id = channel_config["channel_id"] if channel_config else None
    channel_status = f"<#{channel_id}>" if channel_id else "not set — use `/dracula-setchannel` to configure it"

    embed = discord.Embed(
        title="Dracula Daily Bot",
        description=(
            "This bot checks [Dracula Daily](https://draculadaily.substack.com/) "
            "every 3 hours and posts new entries to a channel of your choice."
        ),
        color=DRACULA_RED,
    )
    embed.set_thumbnail(url=DRACULA_LOGO)
    embed.add_field(name="Posting channel", value=channel_status, inline=False)
    embed.add_field(
        name="Commands",
        value=(
            "`/dracula-setchannel` — Set the current channel as the posting channel *(requires Manage Channels)*\n"
            "`/dracula-check` — Manually trigger a feed check *(requires Manage Channels)*\n"
            "`/dracula-help` — Show this message"
        ),
        inline=False,
    )
    embed.set_footer(text="Only visible to you")

    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="dracula-setchannel", description="Set this channel as the Dracula Daily posting channel.")
@app_commands.checks.has_permissions(manage_channels=True)
async def setchannel(interaction: discord.Interaction) -> None:
    state = load_state()
    if "channels" not in state:
        state["channels"] = {}
    guild_id = str(interaction.guild_id)
    state["channels"][guild_id] = {
        "channel_id": interaction.channel_id,
        "last_seen_guid": None
    }
    save_state(state)
    log.info("Channel set to %s for guild %s by %s.", interaction.channel_id, guild_id, interaction.user)
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


@tree.command(name="dracula-check", description="Manually trigger a feed check for new Dracula Daily posts.")
@app_commands.checks.has_permissions(manage_channels=True)
async def manual_check(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    await check_feed()
    await interaction.followup.send("Feed check completed!", ephemeral=True)


@manual_check.error
async def manual_check_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You need the **Manage Channels** permission to use this command.",
            ephemeral=True,
        )





@tasks.loop(hours=3)
async def check_feed() -> None:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    log.info("Checking Dracula Daily feed... [%s]", now)
    state = load_state()

    channels_config = state.get("channels", {})
    if not channels_config:
        log.warning("No channels configured. Use /dracula-setchannel in your servers.")
        return

    entry = fetch_latest_entry()
    if entry is None:
        return

    guid = entry.get("id") or entry.get("link")
    embed = build_embed(entry)
    
    # Send to all configured channels
    for guild_id, config in channels_config.items():
        channel_id = config["channel_id"]
        last_guid = config.get("last_seen_guid")
        
        # Check if this guild has already seen this post
        if guid == last_guid:
            log.info("Post already sent to guild %s. Skipping.", guild_id)
            continue
        
        try:
            channel = await client.fetch_channel(channel_id)
            await channel.send(embed=embed)
            log.info("Embed sent to channel %s (guild %s).", channel_id, guild_id)
            
            # Update last seen guid for this specific guild
            state["channels"][guild_id]["last_seen_guid"] = guid
        except discord.NotFound:
            log.error("Channel %s not found in guild %s.", channel_id, guild_id)
        except discord.Forbidden:
            log.error("Bot lacks permission to access channel %s in guild %s.", channel_id, guild_id)
        except Exception as e:
            log.error("Error sending to channel %s in guild %s: %s", channel_id, guild_id, e)

    save_state(state)


@check_feed.before_loop
async def before_check_feed() -> None:
    await client.wait_until_ready()


@client.event
async def on_ready() -> None:
    log.info("Logged in as %s (ID: %s)", client.user, client.user.id)
    synced = await tree.sync()
    log.info("Slash commands synced: %s", [cmd.name for cmd in synced])

    if not check_feed.is_running():
        check_feed.start()

    log.info("Feed check scheduled every 3 hours.")
    await check_feed()  # Run immediately on startup


if __name__ == "__main__":
    client.run(config.DISCORD_TOKEN)
