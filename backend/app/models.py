import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def enum_type(cls):
    return Enum(cls, values_callable=lambda items: [item.value for item in items], native_enum=False)


class AccountType(str, enum.Enum):
    checking = "checking"
    savings = "savings"
    credit_card = "credit_card"
    cash = "cash"
    other = "other"


class InstrumentType(str, enum.Enum):
    credit_card = "credit_card"
    debit_card = "debit_card"
    authorized_user_card = "authorized_user_card"
    other = "other"


class ImportStatus(str, enum.Enum):
    uploaded = "uploaded"
    mapped = "mapped"
    normalized = "normalized"
    review_pending = "review_pending"
    confirmed = "confirmed"
    cancelled = "cancelled"
    failed = "failed"


class AmountBehavior(str, enum.Enum):
    signed_amount = "signed_amount"
    debit_credit_columns = "debit_credit_columns"
    charges_positive = "charges_positive"
    charges_negative = "charges_negative"
    credits_positive = "credits_positive"
    credits_negative = "credits_negative"


class Direction(str, enum.Enum):
    inflow = "inflow"
    outflow = "outflow"


class TransactionType(str, enum.Enum):
    expense = "expense"
    income = "income"
    transfer = "transfer"
    credit_card_payment = "credit_card_payment"
    refund = "refund"
    fee = "fee"
    adjustment = "adjustment"
    other = "other"


class DuplicateStatus(str, enum.Enum):
    new = "new"
    duplicate = "duplicate"
    possible_duplicate = "possible_duplicate"


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    edited = "edited"
    approved = "approved"
    skipped = "skipped"


class MatchField(str, enum.Enum):
    description = "description"
    merchant = "merchant"
    account = "account"
    account_instrument = "account_instrument"
    source_category = "source_category"
    amount = "amount"
    direction = "direction"
    cardholder_name = "cardholder_name"
    card_last_four = "card_last_four"


class MatchOperator(str, enum.Enum):
    contains = "contains"
    equals = "equals"
    starts_with = "starts_with"
    regex = "regex"
    greater_than = "greater_than"
    less_than = "less_than"


class Cadence(str, enum.Enum):
    monthly = "monthly"
    weekly = "weekly"
    annual = "annual"
    quarterly = "quarterly"
    irregular = "irregular"


class RecurringStatus(str, enum.Enum):
    suggested = "suggested"
    approved = "approved"
    rejected = "rejected"
    inactive = "inactive"


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))


class Institution(Base, IdMixin, TimestampMixin):
    __tablename__ = "institutions"
    __table_args__ = (UniqueConstraint("user_id", "normalized_name"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    normalized_name: Mapped[str] = mapped_column(String(160))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Account(Base, IdMixin, TimestampMixin):
    __tablename__ = "accounts"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL"), index=True
    )
    account_type: Mapped[AccountType] = mapped_column(enum_type(AccountType))
    last_four: Mapped[str | None] = mapped_column(String(4))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    statement_cycle_day: Mapped[int | None] = mapped_column(Integer)
    payment_due_day: Mapped[int | None] = mapped_column(Integer)
    institution = relationship("Institution", lazy="joined")
    instruments = relationship("AccountInstrument", cascade="all, delete-orphan")


class AccountInstrument(Base, IdMixin, TimestampMixin):
    __tablename__ = "account_instruments"
    __table_args__ = (UniqueConstraint("account_id", "source_identifier"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    instrument_type: Mapped[InstrumentType] = mapped_column(enum_type(InstrumentType))
    display_name: Mapped[str] = mapped_column(String(160))
    cardholder_name: Mapped[str | None] = mapped_column(String(160))
    last_four: Mapped[str | None] = mapped_column(String(4))
    source_identifier: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ImportFile(Base, IdMixin, TimestampMixin):
    __tablename__ = "import_files"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL"), index=True
    )
    account_type: Mapped[AccountType | None] = mapped_column(enum_type(AccountType))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(500))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[ImportStatus] = mapped_column(enum_type(ImportStatus), default=ImportStatus.uploaded)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_row_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_row_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    headers_json: Mapped[list] = mapped_column(JSON, default=list)
    sample_rows_json: Mapped[list] = mapped_column(JSON, default=list)
    proposed_mapping_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_duplicate_file: Mapped[bool] = mapped_column(Boolean, default=False)
    institution = relationship("Institution", lazy="joined")


class ImportMapping(Base, IdMixin, TimestampMixin):
    __tablename__ = "import_mappings"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    account_type: Mapped[AccountType] = mapped_column(enum_type(AccountType))
    mapping_name: Mapped[str] = mapped_column(String(160))
    header_signature: Mapped[str] = mapped_column(String(64), index=True)
    date_column: Mapped[str | None] = mapped_column(String(255))
    post_date_column: Mapped[str | None] = mapped_column(String(255))
    description_column: Mapped[str | None] = mapped_column(String(255))
    merchant_column: Mapped[str | None] = mapped_column(String(255))
    amount_column: Mapped[str | None] = mapped_column(String(255))
    debit_column: Mapped[str | None] = mapped_column(String(255))
    credit_column: Mapped[str | None] = mapped_column(String(255))
    category_column: Mapped[str | None] = mapped_column(String(255))
    transaction_id_column: Mapped[str | None] = mapped_column(String(255))
    notes_column: Mapped[str | None] = mapped_column(String(255))
    card_number_column: Mapped[str | None] = mapped_column(String(255))
    card_last_four_column: Mapped[str | None] = mapped_column(String(255))
    cardholder_name_column: Mapped[str | None] = mapped_column(String(255))
    account_suffix_column: Mapped[str | None] = mapped_column(String(255))
    amount_behavior: Mapped[AmountBehavior] = mapped_column(enum_type(AmountBehavior))
    institution = relationship("Institution", lazy="joined")


class Category(Base, IdMixin, TimestampMixin):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    subcategories = relationship("Subcategory", cascade="all, delete-orphan")


class Subcategory(Base, IdMixin, TimestampMixin):
    __tablename__ = "subcategories"
    __table_args__ = (UniqueConstraint("category_id", "name"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ProviderCategoryMapping(Base, IdMixin, TimestampMixin):
    __tablename__ = "provider_category_mappings"
    __table_args__ = (UniqueConstraint("user_id", "institution_id", "source_category"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    source_category: Mapped[str] = mapped_column(String(160))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"))
    subcategory_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subcategories.id"))
    institution = relationship("Institution", lazy="joined")


class Rule(Base, IdMixin, TimestampMixin):
    __tablename__ = "rules"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    match_field: Mapped[MatchField] = mapped_column(enum_type(MatchField))
    match_operator: Mapped[MatchOperator] = mapped_column(enum_type(MatchOperator))
    match_value: Mapped[str] = mapped_column(String(500))
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"))
    subcategory_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subcategories.id"))
    transaction_type: Mapped[TransactionType | None] = mapped_column(enum_type(TransactionType))
    is_excluded_from_spending: Mapped[bool | None] = mapped_column(Boolean)
    mark_as_recurring: Mapped[bool | None] = mapped_column(Boolean)
    merchant_name_override: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)


class TransactionColumns:
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    account_instrument_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("account_instruments.id"), index=True)
    transaction_date: Mapped[date] = mapped_column(Date)
    posted_date: Mapped[date | None] = mapped_column(Date)
    description_original: Mapped[str] = mapped_column(Text)
    description_clean: Mapped[str] = mapped_column(Text)
    merchant_name: Mapped[str | None] = mapped_column(String(255))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    direction: Mapped[Direction] = mapped_column(enum_type(Direction))
    transaction_type: Mapped[TransactionType] = mapped_column(enum_type(TransactionType))
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), index=True)
    subcategory_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subcategories.id"), index=True)
    source_category: Mapped[str | None] = mapped_column(String(160))
    source_card_identifier: Mapped[str | None] = mapped_column(String(64))
    card_last_four: Mapped[str | None] = mapped_column(String(4))
    cardholder_name: Mapped[str | None] = mapped_column(String(160))
    is_excluded_from_spending: Mapped[bool] = mapped_column(Boolean, default=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    dedupe_key: Mapped[str] = mapped_column(String(64), index=True)
    provider_transaction_id: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)


class DraftTransaction(Base, IdMixin, TimestampMixin, TransactionColumns):
    __tablename__ = "draft_transactions"
    import_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_files.id", ondelete="CASCADE"), index=True)
    row_index: Mapped[int] = mapped_column(Integer)
    raw_row_json: Mapped[dict] = mapped_column(JSON)
    recurring_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_status: Mapped[DuplicateStatus] = mapped_column(enum_type(DuplicateStatus), default=DuplicateStatus.new)
    applied_rule_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rules.id"))
    review_status: Mapped[ReviewStatus] = mapped_column(enum_type(ReviewStatus), default=ReviewStatus.pending)


class Transaction(Base, IdMixin, TimestampMixin, TransactionColumns):
    __tablename__ = "transactions"
    __table_args__ = (Index("ix_transaction_user_date", "user_id", "transaction_date"),)
    import_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("import_files.id", ondelete="SET NULL"), index=True)
    recurring_series_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recurring_series.id"))


class RecurringSeries(Base, IdMixin, TimestampMixin):
    __tablename__ = "recurring_series"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    merchant_name: Mapped[str] = mapped_column(String(255))
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"))
    subcategory_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subcategories.id"))
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    amount_variability: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    cadence: Mapped[Cadence] = mapped_column(enum_type(Cadence))
    status: Mapped[RecurringStatus] = mapped_column(enum_type(RecurringStatus), default=RecurringStatus.suggested)
    first_seen_date: Mapped[date] = mapped_column(Date)
    last_seen_date: Mapped[date] = mapped_column(Date)
    next_expected_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
