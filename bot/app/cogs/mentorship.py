"""
Mentorship management commands.

Permission model
  /mentorship create      → any verified user (becomes first lead mentor)
  /mentorship add         → lead mentors add mentors/mentees
                            creator always retains add/remove rights regardless of own role
  /mentorship remove      → same as add
  /mentorship delete      → server administrators only
  /mentorship list        → anyone
  /mentorship members     → anyone
  /mentorship set-channel → lead mentors only
"""

from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.orm import Session

from shared.database import SessionLocal
from shared.models import Mentorship, MentorshipMember, UserIdentity, UserRole

_ROLE_LABELS = {
    UserRole.lead_mentor: "Lead Mentor",
    UserRole.mentor:      "Mentor",
    UserRole.mentee:      "Mentee",
}


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _get_identity(db: Session, discord_id: str) -> UserIdentity | None:
    return db.query(UserIdentity).filter(UserIdentity.discord_id == discord_id).first()


def _get_mentorship_by_name(db: Session, guild_id: str, name: str) -> Mentorship | None:
    return db.query(Mentorship).filter(
        Mentorship.discord_guild_id == guild_id,
        Mentorship.name             == name,
    ).first()


def _get_member_entry(db: Session, mentorship_id: int, osu_user_id: int) -> MentorshipMember | None:
    return db.query(MentorshipMember).filter(
        MentorshipMember.mentorship_id == mentorship_id,
        MentorshipMember.osu_user_id   == osu_user_id,
    ).first()


def _is_lead_mentor(db: Session, mentorship_id: int, discord_id: str) -> bool:
    identity = _get_identity(db, discord_id)
    if not identity:
        return False
    entry = _get_member_entry(db, mentorship_id, identity.osu_user_id)
    return entry is not None and entry.role == UserRole.lead_mentor


def _is_creator(mentorship: Mentorship, discord_id: str) -> bool:
    """
    True if this Discord user created the mentorship.
    Creators keep creator-level permissions regardless of their current role —
    a creator demoted to mentee can still add/remove lead mentors.
    Falls back to True for legacy rows where creator_discord_id is NULL.
    """
    if mentorship.creator_discord_id is None:
        return True   # legacy: any lead mentor acts as creator
    return mentorship.creator_discord_id == discord_id


def _has_lead_perms(db: Session, mentorship: Mentorship, discord_id: str) -> bool:
    """True if the user may perform lead-mentor-level membership actions."""
    return _is_creator(mentorship, discord_id) or _is_lead_mentor(db, mentorship.id, discord_id)


# ── Autocomplete ───────────────────────────────────────────────────────────────

async def _mentorship_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> List[app_commands.Choice[str]]:
    db = SessionLocal()
    try:
        rows = (
            db.query(Mentorship)
            .filter(
                Mentorship.discord_guild_id == str(interaction.guild_id),
                Mentorship.name.ilike(f"%{current}%"),
            )
            .order_by(Mentorship.name)
            .limit(25)
            .all()
        )
        return [app_commands.Choice(name=r.name, value=r.name) for r in rows]
    finally:
        db.close()


async def _my_mentorships_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> List[app_commands.Choice[str]]:
    """Mentorships where the invoker has lead-level permissions."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Mentorship)
            .filter(
                Mentorship.discord_guild_id == str(interaction.guild_id),
                Mentorship.name.ilike(f"%{current}%"),
            )
            .order_by(Mentorship.name)
            .limit(50)
            .all()
        )
        result = []
        for m in rows:
            if _has_lead_perms(db, m, str(interaction.user.id)):
                result.append(app_commands.Choice(name=m.name, value=m.name))
            if len(result) == 25:
                break
        return result
    finally:
        db.close()


# ── Cog ────────────────────────────────────────────────────────────────────────

class MentorshipCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="mentorship", description="Manage mentorships in this server")

    # ── Create ─────────────────────────────────────────────────────────────────

    @group.command(name="create", description="Create a new mentorship group (you become its first lead mentor)")
    @app_commands.describe(name="Name of the mentorship")
    async def create(self, interaction: discord.Interaction, name: str):
        db: Session = SessionLocal()
        try:
            identity = _get_identity(db, str(interaction.user.id))
            if not identity:
                await interaction.response.send_message(
                    "You need to verify your osu! account first. Run `/verify`.", ephemeral=True
                )
                return

            if db.query(Mentorship).filter(
                Mentorship.discord_guild_id == str(interaction.guild_id),
                Mentorship.name             == name,
            ).first():
                await interaction.response.send_message(
                    f"A mentorship named **{name}** already exists.", ephemeral=True
                )
                return

            m = Mentorship(
                name=name,
                discord_guild_id=str(interaction.guild_id),
                creator_discord_id=str(interaction.user.id),
            )
            db.add(m)
            db.flush()
            db.add(MentorshipMember(
                mentorship_id=m.id,
                osu_user_id=identity.osu_user_id,
                role=UserRole.lead_mentor,
            ))
            db.commit()
            await interaction.response.send_message(
                f"✅ Created **{name}**. You've been added as Lead Mentor."
            )
        finally:
            db.close()

    # ── List ───────────────────────────────────────────────────────────────────

    @group.command(name="list", description="List all mentorships in this server")
    async def list_mentorships(self, interaction: discord.Interaction):
        db: Session = SessionLocal()
        try:
            rows = db.query(Mentorship).filter(
                Mentorship.discord_guild_id == str(interaction.guild_id)
            ).order_by(Mentorship.name).all()
            if not rows:
                await interaction.response.send_message("No mentorships yet.", ephemeral=True)
                return
            lines = [f"• **{m.name}** ({len(m.members)} member(s))" for m in rows]
            await interaction.response.send_message(
                "**Mentorships in this server:**\n" + "\n".join(lines)
            )
        finally:
            db.close()

    # ── Add member ─────────────────────────────────────────────────────────────

    @group.command(name="add", description="Add or update a member in a mentorship")
    @app_commands.describe(
        mentorship_name="Mentorship name",
        user="Discord user to add",
        role="Their role",
    )
    @app_commands.choices(role=[
        app_commands.Choice(name="Lead Mentor", value="lead_mentor"),
        app_commands.Choice(name="Mentor",      value="mentor"),
        app_commands.Choice(name="Mentee",      value="mentee"),
    ])
    @app_commands.autocomplete(mentorship_name=_my_mentorships_autocomplete)
    async def add_member(
        self,
        interaction: discord.Interaction,
        mentorship_name: str,
        user: discord.Member,
        role: str,
    ):
        db: Session = SessionLocal()
        try:
            mentorship = _get_mentorship_by_name(db, str(interaction.guild_id), mentorship_name)
            if not mentorship:
                await interaction.response.send_message(
                    f"Mentorship **{mentorship_name}** not found.", ephemeral=True
                )
                return

            invoker_id = str(interaction.user.id)

            if role == "lead_mentor":
                if not _is_creator(mentorship, invoker_id):
                    await interaction.response.send_message(
                        "Only the mentorship **creator** can add Lead Mentors.", ephemeral=True
                    )
                    return
            else:
                if not _has_lead_perms(db, mentorship, invoker_id):
                    await interaction.response.send_message(
                        "Only **Lead Mentors** (or the creator) can add members.", ephemeral=True
                    )
                    return

            identity = _get_identity(db, str(user.id))
            if not identity:
                await interaction.response.send_message(
                    f"{user.mention} hasn't verified their osu! account yet.", ephemeral=True
                )
                return

            existing = _get_member_entry(db, mentorship.id, identity.osu_user_id)
            if existing:
                old_role      = existing.role
                existing.role = UserRole(role)
                db.commit()
                await interaction.response.send_message(
                    f"Updated {user.mention} (**{identity.osu_username}**): "
                    f"`{old_role.value}` → `{role}` in **{mentorship.name}**"
                )
            else:
                db.add(MentorshipMember(
                    mentorship_id=mentorship.id,
                    osu_user_id=identity.osu_user_id,
                    role=UserRole(role),
                ))
                db.commit()
                await interaction.response.send_message(
                    f"Added {user.mention} (**{identity.osu_username}**) "
                    f"as `{role}` to **{mentorship.name}**"
                )
        finally:
            db.close()

    # ── Remove member ──────────────────────────────────────────────────────────

    @group.command(name="remove", description="Remove a member from a mentorship")
    @app_commands.describe(mentorship_name="Mentorship name", user="Discord user to remove")
    @app_commands.autocomplete(mentorship_name=_my_mentorships_autocomplete)
    async def remove_member(
        self,
        interaction: discord.Interaction,
        mentorship_name: str,
        user: discord.Member,
    ):
        db: Session = SessionLocal()
        try:
            mentorship = _get_mentorship_by_name(db, str(interaction.guild_id), mentorship_name)
            if not mentorship:
                await interaction.response.send_message(
                    f"Mentorship **{mentorship_name}** not found.", ephemeral=True
                )
                return

            invoker_id      = str(interaction.user.id)
            target_identity = _get_identity(db, str(user.id))
            if not target_identity:
                await interaction.response.send_message(
                    f"{user.mention} is not verified.", ephemeral=True
                )
                return

            member = _get_member_entry(db, mentorship.id, target_identity.osu_user_id)
            if not member:
                await interaction.response.send_message(
                    f"{user.mention} is not in **{mentorship.name}**.", ephemeral=True
                )
                return

            if member.role == UserRole.lead_mentor:
                if not _is_creator(mentorship, invoker_id):
                    await interaction.response.send_message(
                        "Only the **creator** can remove Lead Mentors.", ephemeral=True
                    )
                    return
            else:
                if not _has_lead_perms(db, mentorship, invoker_id):
                    await interaction.response.send_message(
                        "Only **Lead Mentors** (or the creator) can remove members.", ephemeral=True
                    )
                    return

            db.delete(member)
            db.commit()
            await interaction.response.send_message(
                f"Removed {user.mention} (**{target_identity.osu_username}**) from **{mentorship.name}**"
            )
        finally:
            db.close()

    # ── Members list ───────────────────────────────────────────────────────────

    @group.command(name="members", description="List all members of a mentorship")
    @app_commands.describe(mentorship_name="Mentorship name")
    @app_commands.autocomplete(mentorship_name=_mentorship_autocomplete)
    async def members(self, interaction: discord.Interaction, mentorship_name: str):
        db: Session = SessionLocal()
        try:
            mentorship = _get_mentorship_by_name(db, str(interaction.guild_id), mentorship_name)
            if not mentorship:
                await interaction.response.send_message(
                    f"Mentorship **{mentorship_name}** not found.", ephemeral=True
                )
                return

            rows = db.query(MentorshipMember).filter(
                MentorshipMember.mentorship_id == mentorship.id
            ).all()
            if not rows:
                await interaction.response.send_message(
                    f"**{mentorship.name}** has no members yet.", ephemeral=True
                )
                return

            osu_ids    = [r.osu_user_id for r in rows]
            identities = {
                i.osu_user_id: i.osu_username
                for i in db.query(UserIdentity).filter(UserIdentity.osu_user_id.in_(osu_ids)).all()
            }

            order       = {UserRole.lead_mentor: 0, UserRole.mentor: 1, UserRole.mentee: 2}
            sorted_rows = sorted(rows, key=lambda r: order.get(r.role, 9))

            lines        = [f"**{mentorship.name}** members:\n"]
            current_role = None
            for r in sorted_rows:
                if r.role != current_role:
                    current_role = r.role
                    lines.append(f"**{_ROLE_LABELS[r.role]}s**")
                username = identities.get(r.osu_user_id, f"osu#{r.osu_user_id}")
                lines.append(f"  • {username}")

            await interaction.response.send_message("\n".join(lines))
        finally:
            db.close()

    # ── Set notification channel ───────────────────────────────────────────────

    @group.command(
        name="set-channel",
        description="Set (or clear) the channel that receives .osz submission notifications",
    )
    @app_commands.describe(
        mentorship_name="Mentorship name",
        channel="Channel to post in — omit to disable notifications",
    )
    @app_commands.autocomplete(mentorship_name=_my_mentorships_autocomplete)
    async def set_channel(
        self,
        interaction: discord.Interaction,
        mentorship_name: str,
        channel: Optional[discord.TextChannel] = None,
    ):
        db: Session = SessionLocal()
        try:
            mentorship = _get_mentorship_by_name(db, str(interaction.guild_id), mentorship_name)
            if not mentorship:
                await interaction.response.send_message(
                    f"Mentorship **{mentorship_name}** not found.", ephemeral=True
                )
                return

            if not _has_lead_perms(db, mentorship, str(interaction.user.id)):
                await interaction.response.send_message(
                    "Only **Lead Mentors** can set the notification channel.", ephemeral=True
                )
                return

            mentorship.notification_channel_id = str(channel.id) if channel else None
            db.commit()

            if channel:
                await interaction.response.send_message(
                    f"✅ Submission notifications for **{mentorship_name}** → {channel.mention}"
                )
            else:
                await interaction.response.send_message(
                    f"✅ Submission notifications disabled for **{mentorship_name}**."
                )
        finally:
            db.close()

    # ── Delete ─────────────────────────────────────────────────────────────────

    @group.command(name="delete", description="Delete a mentorship and all its data (irreversible)")
    @app_commands.describe(mentorship_name="Mentorship name to delete")
    @app_commands.autocomplete(mentorship_name=_mentorship_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def delete_mentorship(self, interaction: discord.Interaction, mentorship_name: str):
        db: Session = SessionLocal()
        try:
            mentorship = _get_mentorship_by_name(db, str(interaction.guild_id), mentorship_name)
            if not mentorship:
                await interaction.response.send_message(
                    f"Mentorship **{mentorship_name}** not found.", ephemeral=True
                )
                return
            name = mentorship.name
            db.delete(mentorship)
            db.commit()
            await interaction.response.send_message(
                f"🗑️ Deleted **{name}**. All members, feedback, and sessions removed."
            )
        finally:
            db.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(MentorshipCog(bot))
