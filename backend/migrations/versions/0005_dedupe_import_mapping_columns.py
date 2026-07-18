"""Deduplicate source columns in saved import mappings.

Revision ID: 0005_unique_mapping_columns
Revises: 0004_provider_types
"""

import sqlalchemy as sa
from alembic import op


revision = "0005_unique_mapping_columns"
down_revision = "0004_provider_types"
branch_labels = None
depends_on = None


MAPPING_FIELDS = (
    "date_column",
    "post_date_column",
    "description_column",
    "merchant_column",
    "amount_column",
    "debit_column",
    "credit_column",
    "category_column",
    "provider_type_column",
    "transaction_id_column",
    "notes_column",
    "card_number_column",
    "card_last_four_column",
    "cardholder_name_column",
    "account_suffix_column",
)


def upgrade():
    bind = op.get_bind()
    columns = ", ".join(("id", *MAPPING_FIELDS))
    mappings = bind.execute(sa.text(f"SELECT {columns} FROM import_mappings")).mappings()

    for mapping in mappings:
        assigned_columns: set[str] = set()
        duplicates: dict[str, None] = {}
        for field in MAPPING_FIELDS:
            source_column = mapping[field]
            if not source_column:
                continue
            if source_column in assigned_columns:
                duplicates[field] = None
            else:
                assigned_columns.add(source_column)

        if duplicates:
            assignments = ", ".join(f"{field} = NULL" for field in duplicates)
            bind.execute(
                sa.text(f"UPDATE import_mappings SET {assignments} WHERE id = :mapping_id"),
                {"mapping_id": mapping["id"]},
            )


def downgrade():
    # Removed duplicate assignments cannot be reconstructed safely.
    pass
