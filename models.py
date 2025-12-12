# backend/models.py

from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base

SCHEMA_NAME = "multichat"


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": SCHEMA_NAME}

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(200), nullable=False)
    email = Column(String(200), nullable=False, unique=True, index=True)
    password = Column(String(200), nullable=False)
    role = Column(String(50), nullable=False)  # admin / teacher / student

    student_id = Column(String(50), unique=True, nullable=True)
    staff_id = Column(String(50), unique=True, nullable=True)

    # profile picture URL (stored as /uploads/avatars/xxxx.png)
    avatar_url = Column(String(300), nullable=True)

    classes_owned = relationship(
        "Class",
        back_populates="owner",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email} ({self.role})>"


class Class(Base):
    __tablename__ = "classes"
    __table_args__ = {"schema": SCHEMA_NAME}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    semester = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    code = Column(String(50), nullable=False, unique=True, index=True)

    owner_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA_NAME}.users.id"),
        nullable=False,
    )

    owner = relationship("User", back_populates="classes_owned")
    members = relationship(
        "ClassMember",
        back_populates="class_",
        cascade="all, delete-orphan",
    )
    messages = relationship(
        "Message",
        back_populates="class_",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Class {self.id} {self.name} ({self.code})>"


class ClassMember(Base):
    __tablename__ = "class_members"
    __table_args__ = (
        UniqueConstraint("class_id", "user_id", name="uq_class_user"),
        {"schema": SCHEMA_NAME},
    )

    id = Column(Integer, primary_key=True, index=True)

    class_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA_NAME}.classes.id"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA_NAME}.users.id"),
        nullable=False,
        index=True,
    )

    role = Column(String(50), nullable=False, default="student")  # student / teacher
    status = Column(
        String(50),
        nullable=False,
        default="pending",
    )  # pending / active / removed

    class_ = relationship("Class", back_populates="members")
    user = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<ClassMember class={self.class_id} "
            f"user={self.user_id} {self.role}/{self.status}>"
        )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = {"schema": SCHEMA_NAME}

    id = Column(Integer, primary_key=True, index=True)

    class_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA_NAME}.classes.id"),
        nullable=False,
        index=True,
    )

    channel = Column(String(50), nullable=False, default="general")

    sender_email = Column(String(200), nullable=False)
    sender_name = Column(String(200), nullable=False)

    content = Column(Text, nullable=False, default="")

    # JSON string with attachment metadata:
    # [
    #   {"filename": "notes.pdf",
    #    "url": "/uploads/abc123_notes.pdf",
    #    "content_type": "application/pdf"},
    #   ...
    # ]
    attachments_json = Column(Text, nullable=False, default="[]")

    timestamp = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    class_ = relationship("Class", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message {self.id} class={self.class_id} ch={self.channel}>"
