"""Create the initial application schema."""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def _common_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        *_common_columns()[:-1],
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "conversations",
        *_common_columns(),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("agent_type", sa.String(length=50), nullable=False, server_default="rag"),
        sa.Column("memory_mode", sa.String(length=50), nullable=False, server_default="none"),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_index("ix_conversations_archived", "conversations", ["archived"])

    op.create_table(
        "messages",
        *_common_columns(),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"])
    op.create_index("ix_messages_user_id", "messages", ["user_id"])
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    op.create_table(
        "documents",
        *_common_columns(),
        sa.Column("document_id", sa.String(length=255), nullable=False),
        sa.Column("document_name", sa.String(length=500), nullable=False),
        sa.Column("document_type", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=1000), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_user_id", "documents", ["user_id"])
    op.create_index("ix_documents_document_id", "documents", ["document_id"])
    op.create_index("ix_documents_checksum", "documents", ["checksum"])

    op.create_table(
        "document_versions",
        *_common_columns(),
        sa.Column("document_id", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("ingestion_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_document_versions_tenant_id", "document_versions", ["tenant_id"])
    op.create_index("ix_document_versions_user_id", "document_versions", ["user_id"])
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
    op.create_index("ix_document_versions_checksum", "document_versions", ["checksum"])

    op.create_table(
        "memories",
        *_common_columns(),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("memory_type", sa.String(length=50), nullable=False),
        sa.Column("memory_key", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding_reference", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_memories_tenant_id", "memories", ["tenant_id"])
    op.create_index("ix_memories_user_id", "memories", ["user_id"])
    op.create_index("ix_memories_conversation_id", "memories", ["conversation_id"])
    op.create_index("ix_memories_memory_type", "memories", ["memory_type"])

    op.create_table(
        "audit_logs",
        *_common_columns(),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("memories")
    op.drop_table("document_versions")
    op.drop_table("documents")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("users")