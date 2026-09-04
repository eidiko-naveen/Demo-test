from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import repository
from database.db import Base
from memory.manager import MemoryManager, MemoryMode


def isolated_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def test_memory_context_is_bounded():
    messages = [type("Message", (), {"role": "user", "content": "x" * 5000})()]
    with patch("memory.manager.get_messages", return_value=messages), \
         patch("memory.manager.get_settings") as settings:
        settings.return_value.memory_window_size = 6
        settings.return_value.memory_context_chars = 100
        context = MemoryManager("session").context(MemoryMode.WINDOW)
    assert len(context) == 100


def test_persistent_memory_includes_previous_user_conversations():
    sessions = isolated_db()
    with patch.object(repository, "db_session", side_effect=lambda: sessions()):
        repository.create_session("session-1", user_id="user-1", tenant_id="tenant-1")
        repository.create_session("session-2", user_id="user-1", tenant_id="tenant-1")
        repository.add_message("session-1", "user", "What was our first decision?", "user-1", "tenant-1")
        repository.add_message("session-1", "assistant", "We decided to prioritize security.", "user-1", "tenant-1")

        with patch("memory.manager.get_settings") as settings:
            settings.return_value.memory_window_size = 20
            settings.return_value.memory_context_chars = 20000
            settings.return_value.max_history_messages = 50
            context = MemoryManager("session-2", user_id="user-1", tenant_id="tenant-1").context(MemoryMode.PERSISTENT)

    assert "What was our first decision?" in context
    assert "We decided to prioritize security." in context
    assert "What was our first decision?" in context
    assert "We decided to prioritize security." in context


def test_memory_retention_prunes_old_messages():
    sessions = isolated_db()
    with patch.object(repository, "db_session", side_effect=lambda: sessions()):
        repository.create_session("session-1", user_id="user-1", tenant_id="tenant-1")
        repository.create_session("session-2", user_id="user-1", tenant_id="tenant-1")

        with sessions() as db:
            db.add_all([
                repository.ChatMessage(
                    session_id="session-1",
                    role="user",
                    content="old memory",
                    created_at=datetime.now(timezone.utc) - timedelta(days=40),
                ),
                repository.ChatMessage(
                    session_id="session-2",
                    role="user",
                    content="recent memory",
                    created_at=datetime.now(timezone.utc) - timedelta(days=2),
                ),
            ])
            db.commit()

        with patch("database.repository.get_settings") as settings:
            settings.return_value.memory_retention_enabled = True
            settings.return_value.memory_retention_days = 30

            repository.purge_expired_messages(user_id="user-1", tenant_id="tenant-1")

        with sessions() as db:
            messages = db.query(repository.ChatMessage).order_by(repository.ChatMessage.created_at.asc()).all()

    assert [message.content for message in messages] == ["recent memory"]
