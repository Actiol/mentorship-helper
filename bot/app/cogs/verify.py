import secrets
import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.orm import Session

from shared.database import SessionLocal
from shared.models import UserIdentity, OAuthState, OAuthFlow
from ..config import settings


class VerifyView(discord.ui.View):
    """A persistent-style view that renders a single link button for osu! OAuth."""

    def __init__(self, url: str):
        # timeout=None keeps the button alive in the ephemeral message without issues
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="Verify with osu!",
                url=url,
                style=discord.ButtonStyle.link,
                emoji="🔗",
            )
        )


class VerifyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="verify", description="Link your osu! account to your Discord account")
    async def verify(self, interaction: discord.Interaction):
        db: Session = SessionLocal()
        try:
            existing = (
                db.query(UserIdentity)
                .filter(UserIdentity.discord_id == str(interaction.user.id))
                .first()
            )
            if existing:
                await interaction.response.send_message(
                    f"✅ You're already verified as **{existing.osu_username}** (#{existing.osu_user_id}).\n"
                    "To re-link a different account, ask an admin to run `/unlink` for you.",
                    ephemeral=True,
                )
                return

            state = secrets.token_urlsafe(32)
            db.add(OAuthState(
                state=state,
                discord_id=str(interaction.user.id),
                flow=OAuthFlow.discord,
            ))
            db.commit()

            url = f"{settings.osu_verify_base_url}?state={state}"
            await interaction.response.send_message(
                "Click the button below to verify your osu! account.\n"
                "⏳ **This link expires in 10 minutes.**",
                view=VerifyView(url),
                ephemeral=True,
            )
        finally:
            db.close()

    @app_commands.command(name="whois", description="Check what osu! account a Discord user is linked to")
    @app_commands.describe(user="The Discord user to look up")
    async def whois(self, interaction: discord.Interaction, user: discord.Member):
        db: Session = SessionLocal()
        try:
            identity = (
                db.query(UserIdentity)
                .filter(UserIdentity.discord_id == str(user.id))
                .first()
            )
            if not identity:
                await interaction.response.send_message(
                    f"{user.mention} hasn't verified their osu! account yet.",
                    ephemeral=True,
                )
            else:
                ts = int(identity.verified_at.timestamp()) if identity.verified_at else 0
                await interaction.response.send_message(
                    f"{user.mention} → **{identity.osu_username}** (#{identity.osu_user_id})\n"
                    f"Verified: <t:{ts}:R>",
                    ephemeral=True,
                )
        finally:
            db.close()

    @app_commands.command(name="unlink", description="[Admin] Unlink a user's osu! account")
    @app_commands.describe(user="The Discord user to unlink")
    @app_commands.default_permissions(administrator=True)
    async def unlink(self, interaction: discord.Interaction, user: discord.Member):
        db: Session = SessionLocal()
        try:
            identity = (
                db.query(UserIdentity)
                .filter(UserIdentity.discord_id == str(user.id))
                .first()
            )
            if not identity:
                await interaction.response.send_message(f"{user.mention} is not verified.", ephemeral=True)
                return
            username = identity.osu_username
            db.delete(identity)
            db.commit()
            await interaction.response.send_message(
                f"🗑️ Unlinked {user.mention} from osu! account **{username}**."
            )
        finally:
            db.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(VerifyCog(bot))
