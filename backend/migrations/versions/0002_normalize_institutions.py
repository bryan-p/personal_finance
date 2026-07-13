"""Normalize financial institutions and replace provider name strings.

Revision ID: 0002_institutions
Revises: 0001_initial
"""

import re
import unicodedata
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0002_institutions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


STARTER_INSTITUTIONS = (
    "Ally Bank",
    "American Express",
    "Bank of America",
    "Barclays",
    "Capital One",
    "Charles Schwab",
    "Chase",
    "Citi",
    "Citizens Bank",
    "Discover",
    "Fidelity",
    "Fifth Third Bank",
    "Goldman Sachs",
    "KeyBank",
    "Navy Federal Credit Union",
    "PNC Bank",
    "Regions Bank",
    "SoFi",
    "Synchrony Bank",
    "TD Bank",
    "Truist",
    "U.S. Bank",
    "USAA",
    "Wells Fargo",
)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def _normalized(value: str) -> str:
    return _clean(value).casefold()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # The original initial revision used metadata.create_all. On a brand-new
    # database it therefore creates the current schema, including this table.
    if inspector.has_table("institutions"):
        return

    op.create_table(
        "institutions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("normalized_name", sa.String(length=160), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "normalized_name", name="uq_institutions_user_normalized_name"),
    )
    op.create_index("ix_institutions_user_id", "institutions", ["user_id"])

    targets = ("accounts", "import_files", "import_mappings", "provider_category_mappings")
    for table_name in targets:
        op.add_column(table_name, sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_index(f"ix_{table_name}_institution_id", table_name, ["institution_id"])
        op.create_foreign_key(
            f"fk_{table_name}_institution_id",
            table_name,
            "institutions",
            ["institution_id"],
            ["id"],
            ondelete="SET NULL" if table_name in ("accounts", "import_files") else None,
        )

    users = [row.id for row in bind.execute(sa.text("SELECT id FROM users"))]
    institution_ids: dict[tuple[uuid.UUID, str], uuid.UUID] = {}
    legacy_rows: dict[str, list] = {}
    for table_name in targets:
        rows = list(
            bind.execute(
                sa.text(
                    f"SELECT id, user_id, provider_name FROM {table_name} "
                    "WHERE provider_name IS NOT NULL"
                )
            )
        )
        legacy_rows[table_name] = rows

    for user_id in users:
        names: dict[str, tuple[str, bool]] = {
            _normalized(name): (name, True) for name in STARTER_INSTITUTIONS
        }
        for rows in legacy_rows.values():
            for row in rows:
                if row.user_id != user_id:
                    continue
                display_name = _clean(row.provider_name or "") or "Unknown Institution"
                names.setdefault(_normalized(display_name), (display_name, False))
        for normalized_name, (display_name, is_system) in names.items():
            institution_id = uuid.uuid4()
            bind.execute(
                sa.text(
                    "INSERT INTO institutions "
                    "(id, user_id, display_name, normalized_name, is_system, is_active) "
                    "VALUES (:id, :user_id, :display_name, :normalized_name, :is_system, true)"
                ),
                {
                    "id": institution_id,
                    "user_id": user_id,
                    "display_name": display_name,
                    "normalized_name": normalized_name,
                    "is_system": is_system,
                },
            )
            institution_ids[(user_id, normalized_name)] = institution_id

    for table_name, rows in legacy_rows.items():
        for row in rows:
            display_name = _clean(row.provider_name or "") or "Unknown Institution"
            bind.execute(
                sa.text(f"UPDATE {table_name} SET institution_id = :institution_id WHERE id = :id"),
                {
                    "institution_id": institution_ids[(row.user_id, _normalized(display_name))],
                    "id": row.id,
                },
            )

    op.alter_column("import_mappings", "institution_id", nullable=False)
    op.alter_column("provider_category_mappings", "institution_id", nullable=False)

    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints("provider_category_mappings"):
        if set(constraint.get("column_names") or ()) == {"user_id", "provider_name", "source_category"}:
            op.drop_constraint(constraint["name"], "provider_category_mappings", type_="unique")
    op.create_unique_constraint(
        "uq_provider_category_mappings_institution_source",
        "provider_category_mappings",
        ["user_id", "institution_id", "source_category"],
    )

    for table_name in targets:
        op.drop_column(table_name, "provider_name")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("institutions"):
        return

    targets = ("accounts", "import_files", "import_mappings", "provider_category_mappings")
    for table_name in targets:
        op.add_column(table_name, sa.Column("provider_name", sa.String(length=160), nullable=True))
        bind.execute(
            sa.text(
                f"UPDATE {table_name} AS target SET provider_name = institutions.display_name "
                "FROM institutions WHERE target.institution_id = institutions.id"
            )
        )

    op.alter_column("import_mappings", "provider_name", nullable=False)
    op.alter_column("provider_category_mappings", "provider_name", nullable=False)
    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints("provider_category_mappings"):
        if set(constraint.get("column_names") or ()) == {"user_id", "institution_id", "source_category"}:
            op.drop_constraint(constraint["name"], "provider_category_mappings", type_="unique")
    op.create_unique_constraint(
        "uq_provider_category_mappings_provider_source",
        "provider_category_mappings",
        ["user_id", "provider_name", "source_category"],
    )

    for table_name in targets:
        inspector = sa.inspect(bind)
        for constraint in inspector.get_foreign_keys(table_name):
            if constraint.get("constrained_columns") == ["institution_id"]:
                op.drop_constraint(constraint["name"], table_name, type_="foreignkey")
        op.drop_index(f"ix_{table_name}_institution_id", table_name=table_name)
        op.drop_column(table_name, "institution_id")
    op.drop_index("ix_institutions_user_id", table_name="institutions")
    op.drop_table("institutions")
