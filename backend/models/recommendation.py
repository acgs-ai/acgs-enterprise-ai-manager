"""
Recommendation Model
SQLAlchemy model for persisted AI recommendations
"""

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    Numeric,
    ForeignKey,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid

from backend.database import Base


class Recommendation(Base):
    """AI-generated recommendation. Blocked recommendations are never stored."""

    __tablename__ = "recommendations"
    # Mirrors the inline CHECKs in database/schema.sql (Postgres auto-names them
    # <table>_<column>_check) and migration 002.
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="recommendations_confidence_check",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'implemented', "
            "'approved', 'pending_approval')",
            name="recommendations_status_check",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain = Column(String(50), nullable=False)
    entity_type = Column(String(50))
    # Free-form string: the API accepts arbitrary entity identifiers
    entity_id = Column(String(255))
    suggestion = Column(Text, nullable=False)
    confidence = Column(Numeric(3, 2))
    rationale = Column(Text)
    # Logical reference to ai_operations.id (no ORM model for that table yet)
    ai_operation_id = Column(UUID(as_uuid=True))
    # pending, accepted, rejected, implemented, approved, pending_approval
    status = Column(String(20), default="pending")
    feedback = Column(Text)
    feedback_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    # "metadata" is reserved on declarative classes, so map it to another attribute
    recommendation_metadata = Column("metadata", JSONB, default=dict)
    governance_check = Column(JSONB)
    generated_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    resolved_at = Column(DateTime(timezone=True))

    def __repr__(self):
        return (
            f"<Recommendation(id={self.id}, domain='{self.domain}', "
            f"status='{self.status}')>"
        )
