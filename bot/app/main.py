import asyncio
import discord
from discord.ext import commands
from .config import settings


class MentorshipBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members  = True
        intents.messages = True
        intents.message_content = True  # needed for the .osz attachment wait_for
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.load_extension("app.cogs.verify")
        await self.load_extension("app.cogs.mentorship")
        await self.load_extension("app.cogs.maps")
        await self.tree.sync()
        print("✅ Slash commands synced")

    async def on_ready(self):
        print(f"🤖 Bot online as {self.user} (ID: {self.user.id})")

    async def on_command_error(self, ctx, error):
        print(f"[error] {error}")


def main():
    bot = MentorshipBot()
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
