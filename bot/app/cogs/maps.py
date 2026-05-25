"""
/submit_map — mentees submit their pre-modded .osz file so mentors can reference it.

Two paths:
  /submit_map mentorship_id beatmapset_id            (then attach the .osz file to the message)
  /submit_map mentorship_id beatmapset_id url:<link> (bot fetches the file from the URL instead)

The bot downloads the file from Discord's CDN (which expires) and POSTs it to the API,
which stores it permanently in the Docker volume.
"""

import io
import discord
from discord import app_commands
from discord.ext import commands
import httpx

from shared.database import SessionLocal
from shared.models import UserIdentity, MentorshipMember
from ..config import settings

DISCORD_MAX_BYTES = 25 * 1024 * 1024  # 25 MB — Discord's attachment limit


class MapsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="submit_map",
        description="Submit the .osz file for a beatmapset you're being mentored on",
    )
    @app_commands.describe(
        mentorship_id="Mentorship ID (from /mentorship list)",
        beatmapset_id="osu! beatmapset ID (the number in the URL)",
        url="Optional: direct download URL if the file is too large to attach (e.g. catbox.moe link)",
    )
    async def submit_map(
        self,
        interaction: discord.Interaction,
        mentorship_id: int,
        beatmapset_id: int,
        url: str = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        db = SessionLocal()
        try:
            # Verify the Discord user is linked
            identity = db.query(UserIdentity).filter(
                UserIdentity.discord_id == str(interaction.user.id)
            ).first()
            if not identity:
                await interaction.followup.send(
                    "You need to verify your osu! account first. Run `/verify`.", ephemeral=True
                )
                return

            # Verify they're a member of this mentorship
            member = db.query(MentorshipMember).filter(
                MentorshipMember.mentorship_id == mentorship_id,
                MentorshipMember.osu_user_id   == identity.osu_user_id,
            ).first()
            if not member:
                await interaction.followup.send(
                    "You're not a member of that mentorship.", ephemeral=True
                )
                return
        finally:
            db.close()

        # ── Path 1: URL provided ───────────────────────────────────────────────
        if url:
            await self._submit_from_url(interaction, identity, mentorship_id, beatmapset_id, url)
            return

        # ── Path 2: Attachment expected ────────────────────────────────────────
        # Discord slash commands don't support file attachments directly in the
        # command parameters, so we prompt the user to reply/follow up with the file.
        # The common pattern is to use a follow-up message that waits for the next
        # attachment from this user in this channel.

        await interaction.followup.send(
            f"📎 Please send your `.osz` file as an attachment in this channel within **60 seconds**.\n"
            f"_(Max size: 25 MB. Larger files: re-run the command with the `url` parameter.)_",
            ephemeral=True,
        )

        def check(msg: discord.Message):
            return (
                msg.author.id   == interaction.user.id
                and msg.channel.id == interaction.channel_id
                and len(msg.attachments) > 0
            )

        try:
            msg: discord.Message = await self.bot.wait_for("message", timeout=60.0, check=check)
        except TimeoutError:
            await interaction.followup.send("⏱️ Timed out. Run the command again.", ephemeral=True)
            return

        attachment = msg.attachments[0]
        if not attachment.filename.endswith(".osz"):
            await interaction.followup.send("❌ That doesn't look like an .osz file.", ephemeral=True)
            return
        if attachment.size > DISCORD_MAX_BYTES:
            await interaction.followup.send(
                f"❌ File is too large ({attachment.size // 1024 // 1024} MB). "
                "Use the `url` parameter with a catbox.moe or similar link instead.",
                ephemeral=True,
            )
            return

        # Download from Discord CDN
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                dl = await client.get(attachment.url)
                dl.raise_for_status()
                file_bytes = dl.content
        except httpx.HTTPError as e:
            await interaction.followup.send(f"❌ Failed to download the file from Discord: {e}", ephemeral=True)
            return

        await self._post_to_api(
            interaction, identity, mentorship_id, beatmapset_id,
            file_bytes=file_bytes,
            filename=attachment.filename,
        )

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _submit_from_url(self, interaction, identity, mentorship_id, beatmapset_id, url):
        """Have the API fetch the file from the URL (avoids Discord size limit)."""
        api_url = f"{settings.api_base_url}/files/beatmapset/from-url"
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    api_url,
                    data={
                        "mentorship_id": mentorship_id,
                        "beatmapset_id": beatmapset_id,
                        "url":           url,
                    },
                    headers={"X-Bot-Secret": settings.api_bot_secret},
                )
                if resp.status_code == 200:
                    info = resp.json()
                    size_mb = info["file_size_bytes"] / 1024 / 1024
                    await interaction.followup.send(
                        f"✅ Submitted **{info['filename']}** ({size_mb:.1f} MB) "
                        f"for beatmapset `{beatmapset_id}`.",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        f"❌ API error {resp.status_code}: {resp.text}", ephemeral=True
                    )
        except httpx.HTTPError as e:
            await interaction.followup.send(f"❌ Failed to reach API: {e}", ephemeral=True)

    async def _post_to_api(self, interaction, identity, mentorship_id, beatmapset_id, file_bytes, filename):
        """Upload the already-downloaded bytes to the API."""
        api_url = f"{settings.api_base_url}/files/beatmapset"
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    api_url,
                    data={
                        "mentorship_id": str(mentorship_id),
                        "beatmapset_id": str(beatmapset_id),
                    },
                    files={"file": (filename, io.BytesIO(file_bytes), "application/octet-stream")},
                    headers={"X-Bot-Secret": settings.api_bot_secret},
                )
                if resp.status_code == 200:
                    info    = resp.json()
                    size_mb = info["file_size_bytes"] / 1024 / 1024
                    await interaction.followup.send(
                        f"✅ Submitted **{filename}** ({size_mb:.1f} MB) "
                        f"for beatmapset `{beatmapset_id}`.",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        f"❌ API error {resp.status_code}: {resp.text}", ephemeral=True
                    )
        except httpx.HTTPError as e:
            await interaction.followup.send(f"❌ Failed to reach API: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MapsCog(bot))
