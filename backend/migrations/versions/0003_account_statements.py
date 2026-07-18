"""Retain compatibility with the retired account-statements branch.

Revision ID: 0003_account_statements
Revises: 0002_institutions

Some development databases applied this revision while the statement-cycle
feature lived on a separate branch. The feature is not part of this branch,
but keeping its revision ID in the graph lets those databases migrate forward
without deleting any statement data. Fresh databases intentionally do no work
at this revision.
"""


revision = "0003_account_statements"
down_revision = "0002_institutions"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
