import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean,
    DateTime, Enum as SAEnum, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    lead_mentor = "lead_mentor"
    mentor      = "mentor"
    mentee      = "mentee"


class Visibility(str, enum.Enum):
    after_discussed = "after_discussed"   # hold until reviewed
    immediate       = "immediate"         # visible right away


class OAuthFlow(str, enum.Enum):
    discord    = "discord"
    userscript = "userscript"


# ── Identity ──────────────────────────────────────────────────────────────────

class UserIdentity(Base):
    """One row per verified user. Created once when they run /verify in Discord."""
    __tablename__ = "user_identities"

    discord_id    = Column(String, primary_key=True)
    osu_user_id   = Column(Integer, unique=True, nullable=False, index=True)
    osu_username  = Column(String, nullable=False)
    verified_at   = Column(DateTime, default=datetime.utcnow, nullable=False)


class OAuthState(Base):
    """Short-lived state tokens for OAuth flows. Cleaned up after use."""
    __tablename__ = "oauth_states"

    state      = Column(String, primary_key=True)
    discord_id = Column(String, nullable=True)   # null for userscript flow
    flow       = Column(SAEnum(OAuthFlow), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ── Mentorship ────────────────────────────────────────────────────────────────

class Mentorship(Base):
    """A mentorship group, scoped to one Discord guild."""
    __tablename__ = "mentorships"

    id                      = Column(Integer, primary_key=True, autoincrement=True)
    name                    = Column(String, nullable=False)
    discord_guild_id        = Column(String, nullable=False, index=True)
    creator_discord_id      = Column(String, nullable=True)
    notification_channel_id = Column(String, nullable=True)   # Discord channel for osz submit embeds
    created_at              = Column(DateTime, default=datetime.utcnow, nullable=False)

    members     = relationship("MentorshipMember",  back_populates="mentorship", cascade="all, delete-orphan")
    discussions = relationship("BeatmapDiscussion", back_populates="mentorship", cascade="all, delete-orphan")
    sessions    = relationship("BeatmapsetSession", back_populates="mentorship", cascade="all, delete-orphan")


class MentorshipMember(Base):
    """Maps an osu! user to a role inside a specific mentorship."""
    __tablename__ = "mentorship_members"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    mentorship_id  = Column(Integer, ForeignKey("mentorships.id", ondelete="CASCADE"), nullable=False)
    osu_user_id    = Column(Integer, nullable=False, index=True)
    role           = Column(SAEnum(UserRole), nullable=False)
    added_at       = Column(DateTime, default=datetime.utcnow, nullable=False)

    mentorship = relationship("Mentorship", back_populates="members")

    __table_args__ = (
        UniqueConstraint("mentorship_id", "osu_user_id", name="uq_member_per_mentorship"),
    )


# ── Beatmapset Session ────────────────────────────────────────────────────────

class BeatmapsetSession(Base):
    """
    One row per (beatmapset, mentorship, mentee).
    Created when a mentee uploads their .osz. Tracks the beatmapset-level
    'reviewed' status — the single toggle that reveals hidden mentor feedback.
    """
    __tablename__ = "beatmapset_sessions"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    beatmapset_id        = Column(Integer, nullable=False, index=True)
    mentorship_id        = Column(Integer, ForeignKey("mentorships.id", ondelete="CASCADE"), nullable=False, index=True)
    mentee_osu_id        = Column(Integer, nullable=False)
    is_discussed         = Column(Boolean, default=False, nullable=False)
    discussed_at         = Column(DateTime, nullable=True)
    discussed_by_osu_id  = Column(Integer, nullable=True)
    created_at           = Column(DateTime, default=datetime.utcnow, nullable=False)

    mentorship = relationship("Mentorship", back_populates="sessions")

    __table_args__ = (
        UniqueConstraint("beatmapset_id", "mentorship_id", "mentee_osu_id", name="uq_beatmapset_session"),
    )


# ── Discussions & Feedback ────────────────────────────────────────────────────

class BeatmapDiscussion(Base):
    """
    Mirrors an osu! beatmap discussion post. Created automatically the first
    time someone leaves feedback on a post.
    NOTE: is_discussed kept for legacy compatibility; the canonical reviewed
    flag is now BeatmapsetSession.is_discussed.
    """
    __tablename__ = "beatmap_discussions"

    osu_discussion_id   = Column(Integer, primary_key=True)
    beatmapset_id       = Column(Integer, nullable=False, index=True)
    mentorship_id       = Column(Integer, ForeignKey("mentorships.id", ondelete="CASCADE"), nullable=False, index=True)
    is_discussed        = Column(Boolean, default=False, nullable=False)  # legacy
    discussed_at        = Column(DateTime, nullable=True)
    discussed_by_osu_id = Column(Integer, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow, nullable=False)

    mentorship = relationship("Mentorship", back_populates="discussions")
    feedback   = relationship("FeedbackEntry", back_populates="discussion", cascade="all, delete-orphan")


class FeedbackEntry(Base):
    """A single piece of mentor/mentee feedback on a discussion post."""
    __tablename__ = "feedback_entries"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    discussion_id  = Column(Integer, ForeignKey("beatmap_discussions.osu_discussion_id", ondelete="CASCADE"), nullable=False)
    mentorship_id  = Column(Integer, ForeignKey("mentorships.id", ondelete="CASCADE"), nullable=False)
    author_osu_id  = Column(Integer, nullable=False)
    author_role    = Column(SAEnum(UserRole), nullable=False)
    content        = Column(Text, nullable=False)
    # Default: mentors hold until reviewed, mentees show immediately
    visibility     = Column(SAEnum(Visibility), nullable=False, default=Visibility.after_discussed)
    # Only mentors/lead_mentors may post anonymously
    is_anonymous   = Column(Boolean, default=False, nullable=False)
    created_at     = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at     = Column(DateTime, nullable=True)

    discussion = relationship("BeatmapDiscussion", back_populates="feedback")
