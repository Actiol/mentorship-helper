import asyncio
import discord
from discord.ext import commands
from loguru import logger
import sys
import aiohttp
from .config import settings


class MentorshipBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True
        super().__init__(command_prefix="!", intents=intents)
        self.startup_retries = 0
        self.max_startup_retries = 5

    async def setup_hook(self):
        await self.load_extension("app.cogs.verify")
        await self.load_extension("app.cogs.mentorship")
        await self.load_extension("app.cogs.maps")
        await self.tree.sync()
        logger.info("✅ Slash commands synced")

    async def on_ready(self):
        logger.info(f"🤖 Bot online as {self.user} (ID: {self.user.id})")
        self.startup_retries = 0  # Reset on successful connection

    async def on_error(self, event, *args, **kwargs):
        logger.error(f"Error in event '{event}':", exc_info=True)


def main():
    logger.info("Starting Discord bot...")
    logger.info(f"Token present: {'✓' if settings.discord_token else '✗'}")
    logger.info(f"Client ID: {settings.discord_client_id}")
    
    bot = MentorshipBot()
    
    # Custom exception handler for connection errors
    async def run_with_retry():
        retry_delay = 1
        max_backoff = 60
        
        while True:
            try:
                await bot.start(settings.discord_token)
            except discord.errors.LoginFailure as e:
                logger.error(f"❌ Login failed — check DISCORD_TOKEN: {e}")
                sys.exit(1)
            except (aiohttp.ClientError, OSError) as e:
                # Network errors (DNS, connection refused, etc.)
                bot.startup_retries += 1
                if bot.startup_retries > bot.max_startup_retries:
                    logger.error(
                        f"❌ Failed to connect after {bot.max_startup_retries} retries. "
                        f"Possible causes:\n"
                        f"  • Docker container has no internet access\n"
                        f"  • Firewall blocking discord.com\n"
                        f"  • DNS not resolving discord.com\n"
                        f"  • discord.com is unavailable\n"
                        f"Last error: {e}"
                    )
                    sys.exit(1)
                logger.warning(
                    f"⏳ Connection attempt {bot.startup_retries}/{bot.max_startup_retries} failed, "
                    f"retrying in {retry_delay}s: {e}"
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_backoff)
            except Exception as e:
                logger.error(f"❌ Unexpected error: {e}", exc_info=True)
                sys.exit(1)
    
    try:
        asyncio.run(run_with_retry())
    except KeyboardInterrupt:
        logger.info("Bot shutdown by user")


if __name__ == "__main__":
    main()
