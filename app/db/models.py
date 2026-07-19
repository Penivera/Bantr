import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, BigInteger
from sqlalchemy.orm import relationship
from app.db.session import Base


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    telegram_username = Column(String(64), index=True)
    wallet_address = Column(String(44))
    created_at = Column(DateTime, default=_now)


class Bet(Base):
    __tablename__ = "bets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bet_id = Column(String(12), unique=True, index=True, nullable=False)
    creator_username = Column(String(64), index=True, nullable=False)
    opponent_username = Column(String(64), index=True)
    creator_wallet = Column(String(44))
    opponent_wallet = Column(String(44))
    chat_id = Column(BigInteger, index=True)
    fixture_id = Column(String(20))
    market = Column(String(32))
    stake_amount = Column(Float, default=0)
    stake_token = Column(String(8), default="USDC")
    status = Column(String(16), default="open", index=True)
    winner = Column(String(64))
    tx_signature = Column(String(88))
    payment_reference = Column(String(44))
    created_at = Column(DateTime, default=_now)
    accepted_at = Column(DateTime)
    settled_at = Column(DateTime)
    cancelled_at = Column(DateTime)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    payment_id = Column(String(12), unique=True, index=True, nullable=False)
    bet_id = Column(String(12), index=True, nullable=False)
    amount = Column(Float, default=0)
    token_symbol = Column(String(8), default="USDC")
    token_mint = Column(String(44))
    recipient = Column(String(44))
    status = Column(String(16), default="pending")
    tx_signature = Column(String(88))
    payer_wallet = Column(String(44))
    instruction = Column(String(32))
    created_at = Column(DateTime, default=_now)
    expires_at = Column(DateTime)


class Refund(Base):
    __tablename__ = "refunds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    refund_id = Column(String(12), unique=True, index=True, nullable=False)
    bet_id = Column(String(12), index=True, nullable=False)
    user_wallet = Column(String(44))
    amount = Column(Float, default=0)
    token_symbol = Column(String(8), default="USDC")
    status = Column(String(16), default="pending")
    claim_tx = Column(String(88))
    created_at = Column(DateTime, default=_now)
    claimed_at = Column(DateTime)


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, unique=True, index=True, nullable=False)
    title = Column(String(128))
    active_fixture = Column(String(20))
    verbosity = Column(String(16), default="standard")
    created_at = Column(DateTime, default=_now)
