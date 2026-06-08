"""
/submit_map — mentees submit their beatmapset for review.

Two submission modes (both accept mentorship_name and beatmapset_id):

  attachment  — user attaches an .osz file directly to the slash command.
                The file is downloaded from Discord's CDN and stored on the
                backend server; the extension serves it as a download.

  url         — user provides a direct download link (catbox.moe etc.).
                The URL is stored as-is; no file is fetched or downloaded.
                The extension renders it as a plain hyperlink.

Both modes post an embed to the configured notification channel (if set).
"""

import io
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger
import httpx

from shared.database import SessionLocal
from shared.models import UserIdentity, MentorshipMember, Mentorship
from ..config import settings

DISCORD_MAX_BYTES = 25 * 1024 * 1024  # 25 MB (Discord's hard cap)


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
        description="Submit your beatmapset for review",
    )
    @app_commands.describe(
        mentorship_name="Mentorship name (type to search)",
        beatmapset_id="osu! beatmapset ID",
        attachment=".osz file — stored on the server and served via the extension (max 25 MB)",
        url="Direct download URL to your .osz (catbox.moe etc.) — stored as-is, no file is downloaded",
    )
    @app_commands.autocomplete(mentorship_name=_member_mentorship_autocomplete)
    async def submit_map(
        self,
        interaction: discord.Interaction,
        mentorship_name: str,
        beatmapset_id: int,
        attachment: Optional[discord.Attachment] = None,
        url: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not attachment and not url:
            await interaction.followup.send(
                "❌ Provide either an `.osz` **file attachment** or a **download URL**.",
                ephemeral=True,
            )
            return

        # ── Resolve membership ─────────────────────────────────────────────────
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

            uploader_osu_id     = identity.osu_user_id
            mentorship_id       = mentorship.id
            notify_channel      = mentorship.notification_channel_id
            mentorship_name_str = mentorship.name
        finally:
            db.close()

        # ── File attachment (takes priority if both provided) ──────────────────
        if attachment:
            if not attachment.filename.endswith(".osz"):
                await interaction.followup.send(
                    "❌ Attachment must be an `.osz` file.", ephemeral=True
                )
                return
            if attachment.size > DISCORD_MAX_BYTES:
                await interaction.followup.send(
                    f"❌ File too large ({attachment.size // 1024 // 1024} MB, max 25 MB). "
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
                    f"❌ Failed to download attachment from Discord: {e}", ephemeral=True
                )
                return

            success = await self._post_to_api(
                interaction, uploader_osu_id, mentorship_id, beatmapset_id,
                file_bytes=file_bytes, filename=attachment.filename,
            )

        # ── URL-only submission ────────────────────────────────────────────────
        else:
            success = await self._submit_url(
                interaction, uploader_osu_id, mentorship_id, beatmapset_id, url
            )

        if success and notify_channel:
            await self._maybe_notify(
                notify_channel, mentorship_name_str,
                beatmapset_id, uploader_osu_id,
            )

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _submit_url(
        self,
        interaction: discord.Interaction,
        uploader_osu_id: int,
        mentorship_id: int,
        beatmapset_id: int,
        url: str,
    ) -> bool:
        """Store a URL submission — no file is fetched or downloaded."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{settings.api_base_url}/files/beatmapset/url",
                    data={
                        "mentorship_id":   str(mentorship_id),
                        "beatmapset_id":   str(beatmapset_id),
                        "url":             url,
                        "uploader_osu_id": str(uploader_osu_id),
                    },
                    headers={"X-Bot-Secret": settings.api_bot_secret},
                )
            if resp.status_code == 200:
                await interaction.followup.send(
                    f"✅ URL submitted for beatmapset `{beatmapset_id}`.\n🔗 {url}",
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
        self,
        interaction: discord.Interaction,
        uploader_osu_id: int,
        mentorship_id: int,
        beatmapset_id: int,
        file_bytes: bytes,
        filename: str,
    ) -> bool:
        """Upload an .osz file to the API for backend storage and serving."""
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