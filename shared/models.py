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
    after_discussed = "after_discussed"
    immediate       = "immediate"


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

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    name               = Column(String, nullable=False)
    discord_guild_id   = Column(String, nullable=False, index=True)
    creator_discord_id = Column(String, nullable=True)   # set at creation; used for permission checks
    created_at         = Column(DateTime, default=datetime.utcnow, nullable=False)

    members     = relationship("MentorshipMember",  back_populates="mentorship", cascade="all, delete-orphan")
    discussions = relationship("BeatmapDiscussion", back_populates="mentorship", cascade="all, delete-orphan")


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


# ── Discussions & Feedback ────────────────────────────────────────────────────

class BeatmapDiscussion(Base):
    """
    Mirrors an osu! beatmap discussion post. Created automatically the first
    time someone leaves feedback on a post. Tracks the 'discussed' status.
    """
    __tablename__ = "beatmap_discussions"

    osu_discussion_id   = Column(Integer, primary_key=True)  # osu! post ID
    beatmapset_id       = Column(Integer, nullable=False, index=True)
    mentorship_id       = Column(Integer, ForeignKey("mentorships.id", ondelete="CASCADE"), nullable=False, index=True)
    is_discussed        = Column(Boolean, default=False, nullable=False)
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
    # mentors are always after_discussed; mentees can choose
    visibility     = Column(SAEnum(Visibility), nullable=False, default=Visibility.after_discussed)
    created_at     = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at     = Column(DateTime, nullable=True)

    discussion = relationship("BeatmapDiscussion", back_populates="feedback")
