from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from config.settings import get_settings

from database.db import (
    ChatMessage,
    ChatSession,
    MemorySummary,
    User,
    UploadedDocument,
    db_session,
)

DEFAULT_USER_ID = "development-user"
DEFAULT_TENANT_ID = "development-tenant"


def record_document(document_id: str, file_name: str, user_id: str = DEFAULT_USER_ID, tenant_id: str = DEFAULT_TENANT_ID):
    with db_session() as db:
        row = db.get(UploadedDocument, (document_id, tenant_id))
        if row is None:
            db.add(UploadedDocument(document_id=document_id, tenant_id=tenant_id, user_id=user_id, file_name=file_name))
        db.commit()


def delete_document(document_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> None:
    with db_session() as db:
        db.execute(
            delete(UploadedDocument).where(
                UploadedDocument.document_id == document_id,
                UploadedDocument.tenant_id == tenant_id,
            )
        )
        db.commit()


def create_session(
    session_id: str,
    title: str = "New conversation",
    user_id: str = DEFAULT_USER_ID,
    tenant_id: str = DEFAULT_TENANT_ID,
):

    with db_session() as db:

        db.add(
            ChatSession(
                id=session_id,
                title=title,
                user_id=user_id,
                tenant_id=tenant_id,
            )
        )
        if db.get(User, user_id) is None:
            db.add(User(id=user_id, tenant_id=tenant_id))

        db.commit()


def list_sessions(limit: int = 30, user_id: str = DEFAULT_USER_ID, tenant_id: str = DEFAULT_TENANT_ID):

    with db_session() as db:

        query = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id, ChatSession.tenant_id == tenant_id)
            .order_by(
                ChatSession.updated_at.desc()
            )
            .limit(limit)
        )

        return list(
            db.scalars(query)
        )


def purge_expired_messages(
    user_id: str = DEFAULT_USER_ID,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> int:
    settings = get_settings()
    if not settings.memory_retention_enabled:
        return 0

    retention_days = int(settings.memory_retention_days or 0)
    if retention_days <= 0:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    with db_session() as db:
        session_ids = db.scalars(
            select(ChatSession.id).where(
                ChatSession.user_id == user_id,
                ChatSession.tenant_id == tenant_id,
            )
        ).all()
        if not session_ids:
            return 0

        result = db.execute(
            delete(ChatMessage).where(
                ChatMessage.session_id.in_(session_ids),
                ChatMessage.created_at < cutoff,
            )
        )
        db.commit()
        return result.rowcount or 0


def get_messages(
    session_id: str,
    limit: int | None = None,
    user_id: str = DEFAULT_USER_ID,
    tenant_id: str = DEFAULT_TENANT_ID,
):
    purge_expired_messages(user_id=user_id, tenant_id=tenant_id)

    with db_session() as db:

        query = select(ChatMessage).where(
            ChatMessage.session_id == session_id,
            ChatMessage.session_id.in_(select(ChatSession.id).where(ChatSession.user_id == user_id, ChatSession.tenant_id == tenant_id)),
        )
        if limit:
            query = query.order_by(
                ChatMessage.created_at.desc()
            ).limit(limit)
            return list(reversed(list(db.scalars(query))))
        query = query.order_by(ChatMessage.created_at.asc())
        return list(db.scalars(query))


def get_user_messages(
    user_id: str = DEFAULT_USER_ID,
    tenant_id: str = DEFAULT_TENANT_ID,
    limit: int | None = None,
    exclude_session_id: str | None = None,
):
    purge_expired_messages(user_id=user_id, tenant_id=tenant_id)

    limit_value = int(limit) if limit is not None else None

    with db_session() as db:

        query = select(ChatMessage).join(ChatSession, ChatSession.id == ChatMessage.session_id).where(
            ChatSession.user_id == user_id,
            ChatSession.tenant_id == tenant_id,
        )

        if exclude_session_id:
            query = query.where(ChatMessage.session_id != exclude_session_id)

        if limit_value:
            query = query.order_by(ChatMessage.created_at.desc()).limit(limit_value)
            return list(reversed(list(db.scalars(query))))

        query = query.order_by(ChatMessage.created_at.asc())
        return list(db.scalars(query))


def add_message(
    session_id: str,
    role: str,
    content: str,
    user_id: str = DEFAULT_USER_ID,
    tenant_id: str = DEFAULT_TENANT_ID,
):

    with db_session() as db:

        session = db.scalar(select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
            ChatSession.tenant_id == tenant_id,
        ))
        if session is None:
            raise PermissionError("Session does not belong to the authenticated user")
        db.add(
            ChatMessage(
                session_id=session_id,
                role=role,
                content=content,
            )
        )

        session.updated_at = (
                datetime.now(
                    timezone.utc
                )
        )

        if (
                role == "user"
                and session.title
                == "New conversation"
            ):

            session.title = (
                    content[:70].strip()
                    or "New conversation"
                )

        db.commit()


        purge_expired_messages(user_id=user_id, tenant_id=tenant_id)


def get_summary(
    session_id: str,
    user_id: str = DEFAULT_USER_ID,
    tenant_id: str = DEFAULT_TENANT_ID,
):

    with db_session() as db:

        row = db.scalar(select(MemorySummary).join(ChatSession).where(
            MemorySummary.session_id == session_id,
            ChatSession.user_id == user_id,
            ChatSession.tenant_id == tenant_id,
        ))

        if row:

            return row.summary

        return ""


def save_summary(
    session_id: str,
    summary: str,
    user_id: str = DEFAULT_USER_ID,
    tenant_id: str = DEFAULT_TENANT_ID,
):

    with db_session() as db:

        row = db.scalar(select(MemorySummary).join(ChatSession).where(
            MemorySummary.session_id == session_id,
            ChatSession.user_id == user_id,
            ChatSession.tenant_id == tenant_id,
        ))
        if not db.scalar(select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id, ChatSession.tenant_id == tenant_id)):
            raise PermissionError("Session does not belong to the authenticated user")

        if row:

            row.summary = summary

        else:

            db.add(
                MemorySummary(
                    session_id=session_id,
                    summary=summary,
                )
            )

        db.commit()


def delete_session(
    session_id: str,
    user_id: str = DEFAULT_USER_ID,
    tenant_id: str = DEFAULT_TENANT_ID,
):

    with db_session() as db:

        db.execute(
            delete(ChatMessage).where(ChatMessage.session_id == session_id, ChatMessage.session_id.in_(select(ChatSession.id).where(ChatSession.user_id == user_id, ChatSession.tenant_id == tenant_id)))
        )

        db.execute(
            delete(MemorySummary).where(MemorySummary.session_id == session_id, MemorySummary.session_id.in_(select(ChatSession.id).where(ChatSession.user_id == user_id, ChatSession.tenant_id == tenant_id)))
        )

        db.execute(
            delete(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id, ChatSession.tenant_id == tenant_id)
        )

        db.commit()