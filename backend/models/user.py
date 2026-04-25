"""
User Model
SQLAlchemy model for User entity
"""

from sqlalchemy import Column, String, DateTime, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from backend.database import Base


class User(Base):
    """User model."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    role = Column(String(50), nullable=False)
    permissions = Column(JSON, default=[])
    team = Column(String(100))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    is_active = Column(Boolean, default=True)

    # Relationships
    tasks = relationship("Task", back_populates="assignee")
    projects = relationship("Project", back_populates="owner")

    def __repr__(self):
        return f"<User(id={self.id}, name='{self.name}', email='{self.email}')>"
