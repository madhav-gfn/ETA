"""Step 6 persistence — each completed agent run stored as its JSON payload
so the dashboard can replay the full alert → attribution → plan chain."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentRunRecord(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_city_time", "city_slug", "completed_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # AgentRunResult JSON
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # Dispatch lifecycle — backs the brief's "signal → intervention" metric.
    # new → dispatched → inspected → closed; each transition stamps its time.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    assigned_to: Mapped[str] = mapped_column(String(128), nullable=True)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
