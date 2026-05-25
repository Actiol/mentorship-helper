"""
Mentorship management commands.

Permission model:
  - /mentorship create  → any verified user (they become the first lead mentor automatically)
  - /mentorship add     → lead mentors may add mentees/mentors; only the creator may add lead mentors
  - /mentorship remove  → lead mentors may remove mentees/mentors; only the creator may remove lead mentors
  - /mentorship delete  → server administrators only
  - /mentorship list    → anyone
  - /mentorship members → anyone

Mentorship names are used throughout (autocomplete replaces raw IDs).
"""

from typing import List

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
    Falls back to True for legacy rows where creator_discord_id is NULL
    (any lead mentor can act as creator on those).
    """
    if mentorship.creator_discord_id is None:
        return True  # legacy: no creator recorded, defer to lead-mentor check
    return mentorship.creator_discord_id == discord_id


# ── Autocomplete ───────────────────────────────────────────────────────────────

async def _mentorship_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> List[app_commands.Choice[str]]:
    """Returns up to 25 mentorship names in this server matching what the user typed."""
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
        return [app_commands.Choice(name=row.name, value=row.name) for row in rows]
    finally:
        db.close()


async def _my_mentorships_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> List[app_commands.Choice[str]]:
    """
    Returns mentorships in this server where the invoker is a lead mentor.
    Used for commands that require lead-mentor permissions.
    """
    db = SessionLocal()
    try:
        identity = _get_identity(db, str(interaction.user.id))
        if not identity:
            return []
        rows = (
            db.query(Mentorship)
            .join(MentorshipMember, MentorshipMember.mentorship_id == Mentorship.id)
            .filter(
                Mentorship.discord_guild_id      == str(interaction.guild_id),
                MentorshipMember.osu_user_id     == identity.osu_user_id,
                MentorshipMember.role            == UserRole.lead_mentor,
                Mentorship.name.ilike(f"%{current}%"),
            )
            .order_by(Mentorship.name)
            .limit(25)
            .all()
        )
        return [app_commands.Choice(name=row.name, value=row.name) for row in rows]
    finally:
        db.close()


# ── Cog ────────────────────────────────────────────────────────────────────────

class MentorshipCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="mentorship", description="Manage mentorships in this server")

    # ── Create ─────────────────────────────────────────────────────────────────

    @group.command(name="create", description="Create a new mentorship group (you become its first lead mentor)")
    @app_commands.describe(name="Name of the mentorship (e.g. 'Batch 3 — Taiko')")
    async def create(self, interaction: discord.Interaction, name: str):
        db: Session = SessionLocal()
        try:
            # Require the invoker to be verified so they can be auto-added
            identity = _get_identity(db, str(interaction.user.id))
            if not identity:
                await interaction.response.send_message(
                    "You need to verify your osu! account before creating a mentorship. "
                    "Run `/verify` first.",
                    ephemeral=True,
                )
                return

            clash = db.query(Mentorship).filter(
                Mentorship.discord_guild_id == str(interaction.guild_id),
                Mentorship.name             == name,
            ).first()
            if clash:
                await interaction.response.send_message(
                    f"A mentorship named **{name}** already exists in this server.", ephemeral=True
                )
                return

            m = Mentorship(
                name=name,
                discord_guild_id=str(interaction.guild_id),
                creator_discord_id=str(interaction.user.id),
            )
            db.add(m)
            db.flush()  # get m.id before adding the member row

            # Auto-add the creator as lead mentor
            db.add(MentorshipMember(
                mentorship_id=m.id,
                osu_user_id=identity.osu_user_id,
                role=UserRole.lead_mentor,
            ))
            db.commit()
            db.refresh(m)

            await interaction.response.send_message(
                f"✅ Created mentorship **{name}**.\n"
                f"You've been added as its Lead Mentor. Use `/mentorship add` to invite others."
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
                await interaction.response.send_message("No mentorships created yet.", ephemeral=True)
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
        role="Their role in this mentorship",
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
                    f"Mentorship **{mentorship_name}** not found in this server.", ephemeral=True
                )
                return

            invoker_discord_id = str(interaction.user.id)

            # Permission check
            if role == "lead_mentor":
                # Only the creator can add a new lead mentor
                if not _is_creator(mentorship, invoker_discord_id):
                    await interaction.response.send_message(
                        "Only the mentorship **creator** can add Lead Mentors.", ephemeral=True
                    )
                    return
            else:
                # Lead mentors can add mentors/mentees
                if not _is_lead_mentor(db, mentorship.id, invoker_discord_id):
                    await interaction.response.send_message(
                        "Only **Lead Mentors** of this mentorship can add members.", ephemeral=True
                    )
                    return

            # Target user must be verified
            identity = _get_identity(db, str(user.id))
            if not identity:
                await interaction.response.send_message(
                    f"{user.mention} hasn't verified their osu! account yet. "
                    f"They need to run `/verify` first.",
                    ephemeral=True,
                )
                return

            existing = _get_member_entry(db, mentorship.id, identity.osu_user_id)
            if existing:
                old_role      = existing.role
                existing.role = UserRole(role)
                db.commit()
                await interaction.response.send_message(
                    f"Updated {user.mention} (**{identity.osu_username}**) "
                    f"from `{old_role.value}` → `{role}` in **{mentorship.name}**"
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
    @app_commands.describe(
        mentorship_name="Mentorship name",
        user="Discord user to remove",
    )
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
                    f"Mentorship **{mentorship_name}** not found in this server.", ephemeral=True
                )
                return

            invoker_discord_id = str(interaction.user.id)
            target_identity = _get_identity(db, str(user.id))
            if not target_identity:
                await interaction.response.send_message(f"{user.mention} is not verified.", ephemeral=True)
                return

            member = _get_member_entry(db, mentorship.id, target_identity.osu_user_id)
            if not member:
                await interaction.response.send_message(
                    f"{user.mention} is not in **{mentorship.name}**.", ephemeral=True
                )
                return

            # Permission check based on the target's current role
            if member.role == UserRole.lead_mentor:
                if not _is_creator(mentorship, invoker_discord_id):
                    await interaction.response.send_message(
                        "Only the mentorship **creator** can remove Lead Mentors.", ephemeral=True
                    )
                    return
            else:
                if not _is_lead_mentor(db, mentorship.id, invoker_discord_id):
                    await interaction.response.send_message(
                        "Only **Lead Mentors** of this mentorship can remove members.", ephemeral=True
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
                    f"Mentorship **{mentorship_name}** not found in this server.", ephemeral=True
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

            lines = [f"**{mentorship.name}** members:\n"]
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
                    f"Mentorship **{mentorship_name}** not found in this server.", ephemeral=True
                )
                return

            name = mentorship.name
            db.delete(mentorship)
            db.commit()
            await interaction.response.send_message(
                f"🗑️ Deleted **{name}**. All members, feedback, and discussion records have been removed."
            )
        finally:
            db.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(MentorshipCog(bot))
