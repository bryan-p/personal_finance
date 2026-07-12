from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models import (
    AccountType,
    AmountBehavior,
    Cadence,
    Direction,
    InstrumentType,
    MatchField,
    MatchOperator,
    RecurringStatus,
    ReviewStatus,
    TransactionType,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORMModel):
    id: UUID
    email: EmailStr
    display_name: str
    created_at: datetime


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    provider_name: str | None = None
    account_type: AccountType
    last_four: str | None = Field(default=None, pattern=r"^\d{4}$")
    currency: str = Field(default="USD", min_length=3, max_length=3)
    is_active: bool = True
    statement_cycle_day: int | None = Field(default=None, ge=1, le=31)
    payment_due_day: int | None = Field(default=None, ge=1, le=31)


class AccountPatch(BaseModel):
    name: str | None = None
    provider_name: str | None = None
    account_type: AccountType | None = None
    last_four: str | None = Field(default=None, pattern=r"^\d{4}$")
    currency: str | None = None
    is_active: bool | None = None
    statement_cycle_day: int | None = Field(default=None, ge=1, le=31)
    payment_due_day: int | None = Field(default=None, ge=1, le=31)


class AccountOut(AccountIn, ORMModel):
    id: UUID
    created_at: datetime
    updated_at: datetime


class InstrumentIn(BaseModel):
    instrument_type: InstrumentType
    display_name: str
    cardholder_name: str | None = None
    last_four: str | None = Field(default=None, pattern=r"^\d{4}$")
    source_identifier: str | None = None
    is_active: bool = True


class InstrumentPatch(BaseModel):
    instrument_type: InstrumentType | None = None
    display_name: str | None = None
    cardholder_name: str | None = None
    last_four: str | None = Field(default=None, pattern=r"^\d{4}$")
    source_identifier: str | None = None
    is_active: bool | None = None


class InstrumentOut(InstrumentIn, ORMModel):
    id: UUID
    account_id: UUID
    created_at: datetime
    updated_at: datetime


MAPPING_FIELDS = [
    "date_column", "post_date_column", "description_column", "merchant_column", "amount_column",
    "debit_column", "credit_column", "category_column", "transaction_id_column", "notes_column",
    "card_number_column", "card_last_four_column", "cardholder_name_column", "account_suffix_column",
]


class MappingIn(BaseModel):
    provider_name: str
    account_type: AccountType
    mapping_name: str
    header_signature: str | None = None
    date_column: str | None = None
    post_date_column: str | None = None
    description_column: str | None = None
    merchant_column: str | None = None
    amount_column: str | None = None
    debit_column: str | None = None
    credit_column: str | None = None
    category_column: str | None = None
    transaction_id_column: str | None = None
    notes_column: str | None = None
    card_number_column: str | None = None
    card_last_four_column: str | None = None
    cardholder_name_column: str | None = None
    account_suffix_column: str | None = None
    amount_behavior: AmountBehavior

    @model_validator(mode="after")
    def validate_required_columns(self):
        if not (self.date_column or self.post_date_column):
            raise ValueError("Map a transaction date or posted date")
        if not self.description_column:
            raise ValueError("Map a description column")
        if self.amount_behavior == AmountBehavior.debit_credit_columns:
            if not (self.debit_column or self.credit_column):
                raise ValueError("Map at least one debit or credit column")
        elif not self.amount_column:
            raise ValueError("Map an amount column")
        return self


class MappingPatch(BaseModel):
    provider_name: str | None = None
    account_type: AccountType | None = None
    mapping_name: str | None = None
    header_signature: str | None = None
    date_column: str | None = None
    post_date_column: str | None = None
    description_column: str | None = None
    merchant_column: str | None = None
    amount_column: str | None = None
    debit_column: str | None = None
    credit_column: str | None = None
    category_column: str | None = None
    transaction_id_column: str | None = None
    notes_column: str | None = None
    card_number_column: str | None = None
    card_last_four_column: str | None = None
    cardholder_name_column: str | None = None
    account_suffix_column: str | None = None
    amount_behavior: AmountBehavior | None = None


class MappingOut(MappingIn, ORMModel):
    id: UUID
    header_signature: str
    created_at: datetime
    updated_at: datetime


class CategoryIn(BaseModel):
    name: str
    description: str | None = None
    is_active: bool = True
    sort_order: int = 0


class SubcategoryIn(CategoryIn):
    category_id: UUID


class CategoryPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class SubcategoryOut(ORMModel):
    id: UUID
    category_id: UUID
    name: str
    description: str | None
    is_system: bool
    is_active: bool
    sort_order: int


class CategoryOut(ORMModel):
    id: UUID
    name: str
    description: str | None
    is_system: bool
    is_active: bool
    sort_order: int
    subcategories: list[SubcategoryOut] = []


class RuleIn(BaseModel):
    name: str
    priority: int = 100
    is_active: bool = True
    match_field: MatchField
    match_operator: MatchOperator
    match_value: str
    category_id: UUID | None = None
    subcategory_id: UUID | None = None
    transaction_type: TransactionType | None = None
    is_excluded_from_spending: bool | None = None
    mark_as_recurring: bool | None = None
    merchant_name_override: str | None = None
    note: str | None = None


class RulePatch(BaseModel):
    name: str | None = None
    priority: int | None = None
    is_active: bool | None = None
    match_field: MatchField | None = None
    match_operator: MatchOperator | None = None
    match_value: str | None = None
    category_id: UUID | None = None
    subcategory_id: UUID | None = None
    transaction_type: TransactionType | None = None
    is_excluded_from_spending: bool | None = None
    mark_as_recurring: bool | None = None
    merchant_name_override: str | None = None
    note: str | None = None


class RuleOut(RuleIn, ORMModel):
    id: UUID
    created_at: datetime
    updated_at: datetime


class DraftPatch(BaseModel):
    account_instrument_id: UUID | None = None
    transaction_date: date | None = None
    posted_date: date | None = None
    description_clean: str | None = None
    merchant_name: str | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    direction: Direction | None = None
    transaction_type: TransactionType | None = None
    category_id: UUID | None = None
    subcategory_id: UUID | None = None
    is_excluded_from_spending: bool | None = None
    is_recurring: bool | None = None
    review_status: ReviewStatus | None = None
    notes: str | None = None


class BulkDraftPatch(BaseModel):
    ids: list[UUID]
    changes: DraftPatch


class TransactionPatch(DraftPatch):
    pass


class BulkTransactionPatch(BaseModel):
    ids: list[UUID]
    changes: TransactionPatch


class ProviderCategoryMappingIn(BaseModel):
    provider_name: str
    source_category: str
    category_id: UUID
    subcategory_id: UUID | None = None


class RecurringManualIn(BaseModel):
    merchant_name: str
    expected_amount: Decimal = Field(gt=0)
    cadence: Cadence
    category_id: UUID | None = None
    subcategory_id: UUID | None = None
    status: RecurringStatus = RecurringStatus.approved
    first_seen_date: date
    last_seen_date: date
    next_expected_date: date | None = None
    amount_variability: Decimal = Decimal("0")
    notes: str | None = None


class RecurringPatch(BaseModel):
    merchant_name: str | None = None
    expected_amount: Decimal | None = Field(default=None, gt=0)
    cadence: Cadence | None = None
    category_id: UUID | None = None
    subcategory_id: UUID | None = None
    status: RecurringStatus | None = None
    next_expected_date: date | None = None
    amount_variability: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class RuleTestIn(BaseModel):
    rule: RuleIn
    limit: int = Field(default=20, ge=1, le=100)


class APIMessage(BaseModel):
    message: str


class ImportMappingLink(BaseModel):
    mapping_id: UUID | None = None
    mapping: MappingIn | None = None


class QueryFilters(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    account_id: UUID | None = None
    account_instrument_id: UUID | None = None
    category_id: UUID | None = None
    subcategory_id: UUID | None = None
    transaction_type: TransactionType | None = None
    search: str | None = None
