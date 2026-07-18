"""Preserve and translate provider transaction types.

Revision ID: 0004_provider_types
Revises: 0003_account_statements
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0004_provider_types"
down_revision = "0003_account_statements"
branch_labels = None
depends_on = None


TRANSACTION_TYPES = (
    "expense",
    "income",
    "transfer",
    "credit_card_payment",
    "refund",
    "fee",
    "adjustment",
    "other",
)


def _column_names(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "provider_type_column" not in _column_names(inspector, "import_mappings"):
        op.add_column(
            "import_mappings",
            sa.Column("provider_type_column", sa.String(length=255), nullable=True),
        )

    for table_name in ("draft_transactions", "transactions"):
        inspector = sa.inspect(bind)
        if "source_transaction_type" not in _column_names(inspector, table_name):
            op.add_column(
                table_name,
                sa.Column("source_transaction_type", sa.String(length=160), nullable=True),
            )

    inspector = sa.inspect(bind)
    if not inspector.has_table("provider_transaction_type_mappings"):
        op.create_table(
            "provider_transaction_type_mappings",
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("source_transaction_type", sa.String(length=160), nullable=False),
            sa.Column(
                "transaction_type",
                sa.Enum(*TRANSACTION_TYPES, native_enum=False),
                nullable=False,
            ),
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id",
                "institution_id",
                "source_transaction_type",
                name="uq_provider_type_mappings_institution_source",
            ),
        )
        op.create_index(
            "ix_provider_transaction_type_mappings_user_id",
            "provider_transaction_type_mappings",
            ["user_id"],
        )
        op.create_index(
            "ix_provider_transaction_type_mappings_institution_id",
            "provider_transaction_type_mappings",
            ["institution_id"],
        )

    inspector = sa.inspect(bind)
    match_field = next(
        column for column in inspector.get_columns("rules") if column["name"] == "match_field"
    )
    if getattr(match_field["type"], "length", None) and match_field["type"].length < 23:
        op.alter_column(
            "rules",
            "match_field",
            existing_type=match_field["type"],
            type_=sa.String(length=23),
            existing_nullable=False,
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("provider_transaction_type_mappings"):
        op.drop_index(
            "ix_provider_transaction_type_mappings_institution_id",
            table_name="provider_transaction_type_mappings",
        )
        op.drop_index(
            "ix_provider_transaction_type_mappings_user_id",
            table_name="provider_transaction_type_mappings",
        )
        op.drop_table("provider_transaction_type_mappings")

    for table_name in ("transactions", "draft_transactions"):
        inspector = sa.inspect(bind)
        if "source_transaction_type" in _column_names(inspector, table_name):
            op.drop_column(table_name, "source_transaction_type")

    inspector = sa.inspect(bind)
    if "provider_type_column" in _column_names(inspector, "import_mappings"):
        op.drop_column("import_mappings", "provider_type_column")
