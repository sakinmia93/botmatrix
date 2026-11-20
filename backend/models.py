import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, DateTime, Text, JSON, BigInteger, Float
)
from sqlalchemy.orm import relationship
from backend.database import Base


class Account(Base):
    """A platform user account (equivalent to the 'Account' object in TPY)."""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    points = Column(Integer, default=100000)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    bots = relationship("Bot", back_populates="owner", cascade="all, delete-orphan")


class Bot(Base):
    """A single Telegram bot registered on the platform."""
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True, index=True)
    # Public opaque numeric identifier. Never expose the internal DB primary key.
    public_id = Column(String(32), unique=True, index=True, nullable=True)
    owner_id = Column(Integer, ForeignKey("accounts.id"))
    name = Column(String, nullable=False)
    token = Column(String, nullable=False, unique=True)
    username = Column(String, nullable=True)
    is_running = Column(Boolean, default=False)
    webhook_set = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)  # soft-delete -> recovery window
    storage_limit_mb = Column(Integer, default=100)
    auto_translate = Column(Boolean, default=False)
    faster_response = Column(Boolean, default=True)

    owner = relationship("Account", back_populates="bots")
    commands = relationship("Command", back_populates="bot", cascade="all, delete-orphan")


class Command(Base):
    """A single command / trigger (e.g. /start) with its TPY-like source code."""
    __tablename__ = "commands"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"))
    trigger = Column(String, nullable=False)  # e.g. "/start", "on_text", "on_callback:buy"
    trigger_type = Column(String, default="command")  # command | text | callback | inline | any
    code = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    bot = relationship("Bot", back_populates="commands")


class UserData(Base):
    """Per-Telegram-user key/value storage scoped to a bot (the `user` / `u` object)."""
    __tablename__ = "user_data"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"))
    telegram_user_id = Column(BigInteger, index=True)
    key = Column(String, index=True)
    value = Column(Text)

    __table_args__ = ()


class BotData(Base):
    """Bot-level (global) key/value storage."""
    __tablename__ = "bot_data"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"))
    key = Column(String, index=True)
    value = Column(Text)


class UserState(Base):
    """Tracks which 'step' / conversation state a Telegram user is in for a bot."""
    __tablename__ = "user_state"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"))
    telegram_user_id = Column(BigInteger, index=True)
    state = Column(String, nullable=True)
    context = Column(JSON, default=dict)


class ScheduledTask(Base):
    """A scheduled command execution (libs.DateAndTime / scheduler)."""
    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"))
    telegram_user_id = Column(BigInteger, nullable=True)
    run_at = Column(DateTime, index=True)
    payload = Column(JSON, default=dict)  # code or command reference + params
    executed = Column(Boolean, default=False)


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"))
    command_trigger = Column(String, nullable=True)
    message = Column(Text)
    traceback = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Resource(Base):
    """Generic named counters/leaderboards for libs.Resources."""
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"))
    name = Column(String, index=True)          # e.g. "coins"
    telegram_user_id = Column(BigInteger, index=True)
    amount = Column(Float, default=0)


class BotMember(Base):
    """Tracks every distinct Telegram user who has messaged a bot (broadcast audience)."""
    __tablename__ = "bot_members"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), index=True)
    telegram_user_id = Column(BigInteger, index=True)
    chat_id = Column(BigInteger)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    first_seen = Column(DateTime, default=datetime.datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = ()


class BroadcastJob(Base):
    """A Broadcast V2 job — powers Bot.broadcast() / pause / resume / speed control."""
    __tablename__ = "broadcast_jobs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), index=True)
    owner_id = Column(Integer, ForeignKey("accounts.id"), index=True)

    mode = Column(String, default="single")        # single | multi | all
    target_bot_ids = Column(JSON, default=list)     # used when mode == multi

    speed = Column(Integer, default=8)               # messages/sec/bot, 1-25
    status = Column(String, default="running")        # running|paused|completed|stopped|failed

    text = Column(Text, nullable=True)
    config = Column(JSON, default=dict)                # extra kwargs for the send call

    total = Column(Integer, default=0)
    sent = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    position = Column(Integer, default=0)               # index into the recipient list (for resume)

    callback_url = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class AccountAPIKey(Base):
    """Hashed account API keys used for explicit cross-account operations."""
    __tablename__ = "account_api_keys"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), index=True, nullable=False)
    key_hash = Column(String(128), unique=True, index=True, nullable=False)
    key_prefix = Column(String(16), nullable=False)
    name = Column(String(100), nullable=False, default="default")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), index=True)
    action = Column(String(100), index=True)
    target_type = Column(String(50), nullable=True)
    target_id = Column(String(100), nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class StorageUsage(Base):
    __tablename__ = "storage_usage"
    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), unique=True, nullable=False)
    used_bytes = Column(BigInteger, default=0)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
