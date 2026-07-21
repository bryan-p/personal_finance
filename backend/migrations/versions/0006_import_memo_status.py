"""Preserve imported memo and status values.

Revision ID: 0006_import_memo_status
Revises: 0005_unique_mapping_columns
"""

import sqlalchemy as sa
from alembic import op


revision = "0006_import_memo_status"
down_revision = "0005_unique_mapping_columns"
branch_labels = None
depends_on = None


def _column_names(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    mapping_columns = _column_names(inspector, "import_mappings")
    if "memo_column" not in mapping_columns:
        op.add_column(
            "import_mappings",
            sa.Column("memo_column", sa.String(length=255), nullable=True),
        )
    if "status_column" not in mapping_columns:
        op.add_column(
            "import_mappings",
            sa.Column("status_column", sa.String(length=255), nullable=True),
        )

    for table_name in ("draft_transactions", "transactions"):
        inspector = sa.inspect(bind)
        transaction_columns = _column_names(inspector, table_name)
        if "memo" not in transaction_columns:
            op.add_column(table_name, sa.Column("memo", sa.Text(), nullable=True))
        if "source_status" not in transaction_columns:
            op.add_column(
                table_name,
                sa.Column("source_status", sa.String(length=160), nullable=True),
            )


def downgrade():
    bind = op.get_bind()

    for table_name in ("transactions", "draft_transactions"):
        inspector = sa.inspect(bind)
        transaction_columns = _column_names(inspector, table_name)
        if "source_status" in transaction_columns:
            op.drop_column(table_name, "source_status")
        if "memo" in transaction_columns:
            op.drop_column(table_name, "memo")

    inspector = sa.inspect(bind)
    mapping_columns = _column_names(inspector, "import_mappings")
    if "status_column" in mapping_columns:
        op.drop_column("import_mappings", "status_column")
    if "memo_column" in mapping_columns:
        op.drop_column("import_mappings", "memo_column")
