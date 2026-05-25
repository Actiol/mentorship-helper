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


class MentorshipCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="mentorship", description="Manage mentorships in this server")

    # ── Create ─────────────────────────────────────────────────────────────────

    @group.command(name="create", description="Create a new mentorship group")
    @app_commands.describe(name="Name of the mentorship (e.g. 'Batch 3 — Taiko')")
    @app_commands.default_permissions(manage_guild=True)
    async def create(self, interaction: discord.Interaction, name: str):
        db: Session = SessionLocal()
        try:
            clash = db.query(Mentorship).filter(
                Mentorship.discord_guild_id == str(interaction.guild_id),
                Mentorship.name             == name,
            ).first()
            if clash:
                await interaction.response.send_message(
                    f"A mentorship named **{name}** already exists (ID `{clash.id}`).", ephemeral=True
                )
                return

            m = Mentorship(name=name, discord_guild_id=str(interaction.guild_id))
            db.add(m)
            db.commit()
            db.refresh(m)
            await interaction.response.send_message(
                f"✅ Created mentorship **{name}** — ID: `{m.id}`\n"
                f"Use `/mentorship add` to assign members."
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
            ).all()
            if not rows:
                await interaction.response.send_message("No mentorships created yet.", ephemeral=True)
                return
            lines = [f"• **{m.name}** — ID `{m.id}` ({len(m.members)} member(s))" for m in rows]
            await interaction.response.send_message("**Mentorships in this server:**\n" + "\n".join(lines))
        finally:
            db.close()

    # ── Add member ─────────────────────────────────────────────────────────────

    @group.command(name="add", description="Add or update a member in a mentorship")
    @app_commands.describe(
        mentorship_id="Mentorship ID (from /mentorship list)",
        user="Discord user to add",
        role="Their role in this mentorship",
    )
    @app_commands.choices(role=[
        app_commands.Choice(name="Lead Mentor", value="lead_mentor"),
        app_commands.Choice(name="Mentor",      value="mentor"),
        app_commands.Choice(name="Mentee",      value="mentee"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def add_member(
        self,
        interaction: discord.Interaction,
        mentorship_id: int,
        user: discord.Member,
        role: str,
    ):
        db: Session = SessionLocal()
        try:
            mentorship = db.query(Mentorship).filter(
                Mentorship.id               == mentorship_id,
                Mentorship.discord_guild_id == str(interaction.guild_id),
            ).first()
            if not mentorship:
                await interaction.response.send_message("Mentorship not found.", ephemeral=True)
                return

            identity = db.query(UserIdentity).filter(
                UserIdentity.discord_id == str(user.id)
            ).first()
            if not identity:
                await interaction.response.send_message(
                    f"{user.mention} hasn't verified their osu! account yet. "
                    f"They need to run `/verify` first.",
                    ephemeral=True,
                )
                return

            existing = db.query(MentorshipMember).filter(
                MentorshipMember.mentorship_id == mentorship_id,
                MentorshipMember.osu_user_id   == identity.osu_user_id,
            ).first()

            if existing:
                old_role     = existing.role
                existing.role = UserRole(role)
                db.commit()
                await interaction.response.send_message(
                    f"Updated {user.mention} (**{identity.osu_username}**) "
                    f"from `{old_role.value}` → `{role}` in **{mentorship.name}**"
                )
            else:
                db.add(MentorshipMember(
                    mentorship_id=mentorship_id,
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
    @app_commands.describe(mentorship_id="Mentorship ID", user="Discord user to remove")
    @app_commands.default_permissions(manage_guild=True)
    async def remove_member(
        self,
        interaction: discord.Interaction,
        mentorship_id: int,
        user: discord.Member,
    ):
        db: Session = SessionLocal()
        try:
            mentorship = db.query(Mentorship).filter(
                Mentorship.id               == mentorship_id,
                Mentorship.discord_guild_id == str(interaction.guild_id),
            ).first()
            if not mentorship:
                await interaction.response.send_message("Mentorship not found.", ephemeral=True)
                return

            identity = db.query(UserIdentity).filter(
                UserIdentity.discord_id == str(user.id)
            ).first()
            if not identity:
                await interaction.response.send_message(f"{user.mention} is not verified.", ephemeral=True)
                return

            member = db.query(MentorshipMember).filter(
                MentorshipMember.mentorship_id == mentorship_id,
                MentorshipMember.osu_user_id   == identity.osu_user_id,
            ).first()
            if not member:
                await interaction.response.send_message(
                    f"{user.mention} is not in **{mentorship.name}**.", ephemeral=True
                )
                return

            db.delete(member)
            db.commit()
            await interaction.response.send_message(
                f"Removed {user.mention} (**{identity.osu_username}**) from **{mentorship.name}**"
            )
        finally:
            db.close()

    # ── Members list ───────────────────────────────────────────────────────────

    @group.command(name="members", description="List all members of a mentorship")
    @app_commands.describe(mentorship_id="Mentorship ID")
    async def members(self, interaction: discord.Interaction, mentorship_id: int):
        db: Session = SessionLocal()
        try:
            mentorship = db.query(Mentorship).filter(
                Mentorship.id               == mentorship_id,
                Mentorship.discord_guild_id == str(interaction.guild_id),
            ).first()
            if not mentorship:
                await interaction.response.send_message("Mentorship not found.", ephemeral=True)
                return

            rows = db.query(MentorshipMember).filter(
                MentorshipMember.mentorship_id == mentorship_id
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

            order  = {UserRole.lead_mentor: 0, UserRole.mentor: 1, UserRole.mentee: 2}
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
    @app_commands.describe(mentorship_id="Mentorship ID to delete")
    @app_commands.default_permissions(administrator=True)
    async def delete_mentorship(self, interaction: discord.Interaction, mentorship_id: int):
        db: Session = SessionLocal()
        try:
            mentorship = db.query(Mentorship).filter(
                Mentorship.id               == mentorship_id,
                Mentorship.discord_guild_id == str(interaction.guild_id),
            ).first()
            if not mentorship:
                await interaction.response.send_message("Mentorship not found.", ephemeral=True)
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
