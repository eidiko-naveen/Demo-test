from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
)
from sqlalchemy import event, inspect, text

from config.settings import get_settings


class Base(DeclarativeBase):
    pass


class User(Base):

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)


class UploadedDocument(Base):

    __tablename__ = "uploaded_documents"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    file_name: Mapped[str] = mapped_column(String(255))


class ChatSession(Base):

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )

    user_id: Mapped[str] = mapped_column(String(128), index=True, default="development-user")
    tenant_id: Mapped[str] = mapped_column(String(128), index=True, default="development-tenant")

    title: Mapped[str] = mapped_column(
        String(200),
        default="New conversation",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ChatMessage(Base):

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "chat_sessions.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    role: Mapped[str] = mapped_column(
        String(20),
    )

    content: Mapped[str] = mapped_column(
        Text,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class MemorySummary(Base):

    __tablename__ = "memory_summaries"

    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "chat_sessions.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    summary: Mapped[str] = mapped_column(
        Text,
        default="",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


settings = get_settings()

connect_args = {}

if settings.database_url.startswith("sqlite"):

    connect_args = {
        "check_same_thread": False,
    }


engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


Base.metadata.create_all(
    engine
)

# Keep existing development databases usable while deployments should use a real migration tool.
with engine.begin() as connection:
    columns = {column["name"] for column in inspect(engine).get_columns("chat_sessions")}
    if "user_id" not in columns:
        connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN user_id VARCHAR(128) NOT NULL DEFAULT 'development-user'"))
    if "tenant_id" not in columns:
        connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN tenant_id VARCHAR(128) NOT NULL DEFAULT 'development-tenant'"))


def db_session():

    return SessionLocal()