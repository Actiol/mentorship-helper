"""
/submit_map — mentees submit their .osz for review.

Paths:
  /submit_map mentorship_name beatmapset_id            → attach .osz to the message
  /submit_map mentorship_name beatmapset_id url:<link> → bot fetches from URL

After a successful upload the bot checks if the mentorship has a notification
channel set (via /mentorship set-channel). If so, it posts an embed with a
mod-count summary fetched from the internal /beatmapset/{id}/discussion-summary
endpoint (which calls the osu! API server-side).
"""

import io
from typing import List

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger
import httpx

from shared.database import SessionLocal
from shared.models import UserIdentity, MentorshipMember, Mentorship
from ..config import settings

DISCORD_MAX_BYTES = 25 * 1024 * 1024


# ── Autocomplete ───────────────────────────────────────────────────────────────

async def _member_mentorship_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> List[app_commands.Choice[str]]:
    db = SessionLocal()
    try:
        identity = (
            db.query(UserIdentity)
            .filter(UserIdentity.discord_id == str(interaction.user.id))
            .first()
        )
        if not identity:
            return []
        rows = (
            db.query(Mentorship)
            .join(MentorshipMember, MentorshipMember.mentorship_id == Mentorship.id)
            .filter(
                Mentorship.discord_guild_id  == str(interaction.guild_id),
                MentorshipMember.osu_user_id == identity.osu_user_id,
                Mentorship.name.ilike(f"%{current}%"),
            )
            .order_by(Mentorship.name)
            .limit(25)
            .all()
        )
        return [app_commands.Choice(name=r.name, value=r.name) for r in rows]
    finally:
        db.close()


# ── Cog ────────────────────────────────────────────────────────────────────────

class MapsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="submit_map",
        description="Submit the .osz for a beatmapset you're being mentored on",
    )
    @app_commands.describe(
        mentorship_name="Mentorship name (type to search)",
        beatmapset_id="osu! beatmapset ID",
        url="Direct download URL if the file is too large to attach (catbox.moe etc.)",
    )
    @app_commands.autocomplete(mentorship_name=_member_mentorship_autocomplete)
    async def submit_map(
        self,
        interaction: discord.Interaction,
        mentorship_name: str,
        beatmapset_id: int,
        url: str = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        db = SessionLocal()
        try:
            identity = db.query(UserIdentity).filter(
                UserIdentity.discord_id == str(interaction.user.id)
            ).first()
            if not identity:
                await interaction.followup.send(
                    "Verify your osu! account first — run `/verify`.", ephemeral=True
                )
                return

            mentorship = (
                db.query(Mentorship)
                .filter(
                    Mentorship.discord_guild_id == str(interaction.guild_id),
                    Mentorship.name             == mentorship_name,
                )
                .first()
            )
            if not mentorship:
                await interaction.followup.send(
                    f"Mentorship **{mentorship_name}** not found.", ephemeral=True
                )
                return

            member = db.query(MentorshipMember).filter(
                MentorshipMember.mentorship_id == mentorship.id,
                MentorshipMember.osu_user_id   == identity.osu_user_id,
            ).first()
            if not member:
                await interaction.followup.send(
                    "You're not a member of that mentorship.", ephemeral=True
                )
                return

            uploader_osu_id = identity.osu_user_id
            mentorship_id   = mentorship.id
            notify_channel  = mentorship.notification_channel_id
            mentorship_name_str = mentorship.name
        finally:
            db.close()

        # ── Path 1: URL provided ───────────────────────────────────────────────
        if url:
            success = await self._submit_from_url(
                interaction, uploader_osu_id, mentorship_id, beatmapset_id, url
            )
            if success and notify_channel:
                await self._maybe_notify(
                    notify_channel, mentorship_name_str,
                    beatmapset_id, uploader_osu_id,
                )
            return

        # ── Path 2: attachment expected ────────────────────────────────────────
        await interaction.followup.send(
            "📎 Attach your `.osz` in this channel within **60 seconds**.\n"
            "_(Max 25 MB — for larger files re-run with the `url` parameter.)_",
            ephemeral=True,
        )

        def check(msg: discord.Message):
            return (
                msg.author.id    == interaction.user.id
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
                f"❌ File too large ({attachment.size // 1024 // 1024} MB). "
                "Use the `url` parameter instead.",
                ephemeral=True,
            )
            return

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                dl = await client.get(attachment.url)
                dl.raise_for_status()
                file_bytes = dl.content
        except httpx.HTTPError as e:
            await interaction.followup.send(
                f"❌ Couldn't download from Discord: {e}", ephemeral=True
            )
            return

        success = await self._post_to_api(
            interaction, uploader_osu_id, mentorship_id, beatmapset_id,
            file_bytes=file_bytes, filename=attachment.filename,
        )
        if success and notify_channel:
            await self._maybe_notify(
                notify_channel, mentorship_name_str,
                beatmapset_id, uploader_osu_id,
            )

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _submit_from_url(
        self, interaction, uploader_osu_id, mentorship_id, beatmapset_id, url
    ) -> bool:
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{settings.api_base_url}/files/beatmapset/from-url",
                    data={
                        "mentorship_id":   str(mentorship_id),
                        "beatmapset_id":   str(beatmapset_id),
                        "url":             url,
                        "uploader_osu_id": str(uploader_osu_id),
                    },
                    headers={"X-Bot-Secret": settings.api_bot_secret},
                )
            if resp.status_code == 200:
                info = resp.json()
                mb   = info["file_size_bytes"] / 1024 / 1024
                await interaction.followup.send(
                    f"✅ Submitted **{info['filename']}** ({mb:.1f} MB) "
                    f"for beatmapset `{beatmapset_id}`.",
                    ephemeral=True,
                )
                return True
            await interaction.followup.send(
                f"❌ API error {resp.status_code}: {resp.text}", ephemeral=True
            )
            return False
        except httpx.HTTPError as e:
            await interaction.followup.send(f"❌ Couldn't reach API: {e}", ephemeral=True)
            return False

    async def _post_to_api(
        self, interaction, uploader_osu_id, mentorship_id, beatmapset_id, file_bytes, filename
    ) -> bool:
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{settings.api_base_url}/files/beatmapset",
                    data={
                        "mentorship_id":   str(mentorship_id),
                        "beatmapset_id":   str(beatmapset_id),
                        "uploader_osu_id": str(uploader_osu_id),
                    },
                    files={"file": (filename, io.BytesIO(file_bytes), "application/octet-stream")},
                    headers={"X-Bot-Secret": settings.api_bot_secret},
                )
            if resp.status_code == 200:
                info = resp.json()
                mb   = info["file_size_bytes"] / 1024 / 1024
                await interaction.followup.send(
                    f"✅ Submitted **{filename}** ({mb:.1f} MB) "
                    f"for beatmapset `{beatmapset_id}`.",
                    ephemeral=True,
                )
                return True
            await interaction.followup.send(
                f"❌ API error {resp.status_code}: {resp.text}", ephemeral=True
            )
            return False
        except httpx.HTTPError as e:
            await interaction.followup.send(f"❌ Couldn't reach API: {e}", ephemeral=True)
            return False

    async def _maybe_notify(
        self,
        channel_id: str,
        mentorship_name: str,
        beatmapset_id: int,
        uploader_osu_id: int,
    ) -> None:
        """Post a submission embed to the configured notification channel."""
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            logger.warning(f"Notification channel {channel_id} not found or inaccessible")
            return

        db = SessionLocal()
        try:
            identity = db.query(UserIdentity).filter(
                UserIdentity.osu_user_id == uploader_osu_id
            ).first()
            username = identity.osu_username if identity else f"user#{uploader_osu_id}"
        finally:
            db.close()

        summary = None
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{settings.api_base_url}/beatmapset/{beatmapset_id}/discussion-summary",
                    headers={"X-Bot-Secret": settings.api_bot_secret},
                )
                if resp.status_code == 200:
                    summary = resp.json()
        except Exception as e:
            logger.warning(f"Couldn't fetch discussion summary: {e}")

        embed = discord.Embed(
            title=f"📦 {summary['title']}" if summary else "📦 Map Submitted for Review",
            color=0x4bd28f,
        )
        embed.add_field(
            name="Mentee",
            value=f"[{username}](https://osu.ppy.sh/users/{uploader_osu_id})",
            inline=True,
        )
        embed.add_field(name="Mentorship", value=mentorship_name, inline=True)
        embed.add_field(
            name="Beatmapset",
            value=f"[#{beatmapset_id}](https://osu.ppy.sh/beatmapsets/{beatmapset_id})",
            inline=True,
        )

        if summary:
            lines = []
            if summary.get("general_count", 0):
                lines.append(f"🗂 General: **{summary['general_count']}**")
            for diff, count in sorted(summary.get("per_diff", {}).items()):
                lines.append(f"  └ {diff}: **{count}**")
            lines.append(f"**Total: {summary.get('total', 0)}**")
            embed.add_field(
                name="Current Mods",
                value="\n".join(lines) if lines else "No mods yet",
                inline=False,
            )

        embed.set_footer(text=f"osu! ID: {uploader_osu_id}")

        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            logger.warning(f"Failed to send notification embed: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(MapsCog(bot))
