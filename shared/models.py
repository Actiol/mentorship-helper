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


class UserIdentity(Base):
    __tablename__ = "user_identities"
    discord_id    = Column(String, primary_key=True)
    osu_user_id   = Column(Integer, unique=True, nullable=False, index=True)
    osu_username  = Column(String, nullable=False)
    verified_at   = Column(DateTime, default=datetime.utcnow, nullable=False)


class OAuthState(Base):
    __tablename__ = "oauth_states"
    state      = Column(String, primary_key=True)
    discord_id = Column(String, nullable=True)
    flow       = Column(SAEnum(OAuthFlow), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Mentorship(Base):
    __tablename__ = "mentorships"
    id                      = Column(Integer, primary_key=True, autoincrement=True)
    name                    = Column(String, nullable=False)
    discord_guild_id        = Column(String, nullable=False, index=True)
    creator_discord_id      = Column(String, nullable=True)
    notification_channel_id = Column(String, nullable=True)
    created_at              = Column(DateTime, default=datetime.utcnow, nullable=False)
    members  = relationship("MentorshipMember",  back_populates="mentorship", cascade="all, delete-orphan")
    # passive_deletes=True: let the DB handle SET NULL on BeatmapDiscussion.mentorship_id
    # rather than having SQLAlchemy load and delete rows (which would cascade to ALL
    # feedback entries regardless of which mentorship they belong to).
    discussions = relationship("BeatmapDiscussion", back_populates="mentorship", passive_deletes=True)
    sessions    = relationship("BeatmapsetSession",  back_populates="mentorship", cascade="all, delete-orphan")


class MentorshipMember(Base):
    __tablename__ = "mentorship_members"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    mentorship_id  = Column(Integer, ForeignKey("mentorships.id", ondelete="CASCADE"), nullable=False)
    osu_user_id    = Column(Integer, nullable=False, index=True)
    role           = Column(SAEnum(UserRole), nullable=False)
    added_at       = Column(DateTime, default=datetime.utcnow, nullable=False)
    mentorship     = relationship("Mentorship", back_populates="members")
    __table_args__  = (
        UniqueConstraint("mentorship_id", "osu_user_id", name="uq_member_per_mentorship"),
    )


class BeatmapsetSession(Base):
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


class BeatmapDiscussion(Base):
    """
    One row per osu! discussion post (NOT per mentorship).

    mentorship_id is the first mentorship that referenced this discussion.
    It is NOT a per-mentorship tracker — all per-mentorship scoping happens
    in FeedbackEntry.  The FK is ON DELETE SET NULL so that deleting one
    mentorship does not destroy feedback entries belonging to others.
    """
    __tablename__ = "beatmap_discussions"
    osu_discussion_id   = Column(Integer, primary_key=True)
    beatmapset_id       = Column(Integer, nullable=False, index=True)
    # Nullable + SET NULL so this row outlives its original mentorship
    mentorship_id       = Column(
        Integer,
        ForeignKey("mentorships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_discussed        = Column(Boolean, default=False, nullable=False)  # legacy per-discussion flag
    discussed_at        = Column(DateTime, nullable=True)
    discussed_by_osu_id = Column(Integer, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow, nullable=False)
    mentorship = relationship("Mentorship", back_populates="discussions")
    feedback   = relationship("FeedbackEntry", back_populates="discussion", cascade="all, delete-orphan")


class FeedbackEntry(Base):
    __tablename__ = "feedback_entries"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    discussion_id  = Column(Integer, ForeignKey("beatmap_discussions.osu_discussion_id", ondelete="CASCADE"), nullable=False)
    mentorship_id  = Column(Integer, ForeignKey("mentorships.id", ondelete="CASCADE"), nullable=False)
    author_osu_id  = Column(Integer, nullable=False)
    author_role    = Column(SAEnum(UserRole), nullable=False)
    content        = Column(Text, nullable=False)
    visibility     = Column(SAEnum(Visibility), nullable=False, default=Visibility.after_discussed)
    is_anonymous   = Column(Boolean, default=False, nullable=False)
    # True when posted in global mode — always visible regardless of review status
    is_global      = Column(Boolean, default=False, nullable=False, server_default="false")
    # Edit tracking
    edit_count     = Column(Integer, default=0, nullable=False, server_default="0")
    created_at     = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at     = Column(DateTime, nullable=True)
    discussion = relationship("BeatmapDiscussion", back_populates="feedback")