import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN: str = os.environ.get("DISCORD_TOKEN", "")
FEED_URL: str = "https://draculadaily.substack.com/feed"
CHECK_HOUR_UTC: int = 8  # 08:00 UTC

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN is not set. Check your .env file.")
