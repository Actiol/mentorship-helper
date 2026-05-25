import asyncio
import discord
from discord.ext import commands
from loguru import logger
from .config import settings


class MentorshipBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.load_extension("app.cogs.verify")
        await self.load_extension("app.cogs.mentorship")
        await self.load_extension("app.cogs.maps")
        await self.tree.sync()
        logger.info("✅ Slash commands synced")

    async def on_ready(self):
        logger.info(f"🤖 Bot online as {self.user} (ID: {self.user.id})")

    async def on_command_error(self, ctx, error):
        logger.error(f"Command error: {error}", exc_info=True)


def main():
    logger.info("Starting Discord bot...")
    bot = MentorshipBot()
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
