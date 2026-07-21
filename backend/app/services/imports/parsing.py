import csv
import hashlib
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from dateutil import parser as date_parser


HEADER_ALIASES = {
    "date_column": ["transaction date", "trans date", "date", "effective date"],
    "post_date_column": ["post date", "posted date", "posting date"],
    "description_column": ["description", "details", "memo", "transaction", "name"],
    "memo_column": ["original description", "extended description", "memo"],
    "merchant_column": ["merchant", "payee"],
    "amount_column": ["amount", "transaction amount"],
    "debit_column": ["debit", "withdrawal", "charge"],
    "credit_column": ["credit", "deposit", "payment"],
    "category_column": ["category", "classification"],
    "provider_type_column": ["type", "transaction type", "activity type"],
    "status_column": ["status", "transaction status", "state"],
    "transaction_id_column": ["transaction id", "reference number", "reference", "id"],
    "notes_column": ["notes", "note"],
    "card_number_column": ["card number", "account number"],
    "card_last_four_column": ["card last four", "last 4", "last four"],
    "cardholder_name_column": ["cardholder", "authorized user", "employee name"],
    "account_suffix_column": ["account suffix", "card", "account"],
}

KNOWN_SIGNATURES = [
    ({"transaction date", "post date", "description", "category", "type", "amount"}, "Chase"),
    ({"date", "description", "amount", "running bal."}, "Bank of America"),
    ({"date", "description", "card member", "account #", "amount"}, "American Express"),
    ({"trans. date", "post date", "description", "amount", "category"}, "Capital One"),
]


def decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unsupported CSV encoding")


def parse_csv(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = decode_csv(content)
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [str(value).strip() for value in (reader.fieldnames or []) if value is not None]
    if not headers:
        raise ValueError("The CSV does not contain a header row")
    rows = [{str(k).strip(): (v or "").strip() for k, v in row.items() if k} for row in reader]
    return headers, rows


def normalize_header_name(header: str) -> str:
    return re.sub(r"\s+", " ", header.strip().casefold())


def header_signature(headers: list[str]) -> str:
    normalized = "|".join(sorted(normalize_header_name(header) for header in headers))
    return hashlib.sha256(normalized.encode()).hexdigest()


def resolve_header_name(saved_header: str | None, headers: list[str]) -> str | None:
    if not saved_header:
        return None
    normalized_headers = {normalize_header_name(header): header for header in headers}
    return normalized_headers.get(normalize_header_name(saved_header))


def file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _score_header(header: str, aliases: list[str]) -> float:
    normalized = re.sub(r"[_-]+", " ", header.strip().lower())
    for index, alias in enumerate(aliases):
        preference = min(index, 5) * 0.015
        if normalized == alias:
            return 1.0 - preference
        if alias in normalized or normalized in alias:
            return 0.75 - preference
    return 0.0


def detect_mapping(headers: list[str], sample_rows: list[dict]) -> dict:
    detected: dict[str, str | float] = {}
    confidence: dict[str, float] = {}
    candidates = []
    for field_index, (field, aliases) in enumerate(HEADER_ALIASES.items()):
        for header_index, header in enumerate(headers):
            score = _score_header(header, aliases)
            if score > 0:
                candidates.append((-score, field_index, header_index, field, header))
    assigned_fields: set[str] = set()
    assigned_headers: set[str] = set()
    for negative_score, _, _, field, header in sorted(candidates):
        if field in assigned_fields or header in assigned_headers:
            continue
        detected[field] = header
        confidence[field] = round(-negative_score, 3)
        assigned_fields.add(field)
        assigned_headers.add(header)
    if "description_column" not in detected and "memo_column" in detected:
        detected["description_column"] = detected.pop("memo_column")
        confidence["description_column"] = confidence.pop("memo_column")
    if "amount_column" not in detected and not ({"debit_column", "credit_column"} <= detected.keys()):
        for header in headers:
            if header in assigned_headers:
                continue
            values = [row.get(header, "") for row in sample_rows[:10]]
            if values and sum(can_parse_amount(v) for v in values) / len(values) >= 0.8:
                detected["amount_column"] = header
                confidence["amount_column"] = 0.45
                assigned_headers.add(header)
                break
    detected["amount_behavior"] = (
        "debit_credit_columns"
        if detected.get("debit_column") or detected.get("credit_column")
        else "signed_amount"
    )
    detected["confidence"] = confidence
    return detected


def detect_provider(headers: list[str]) -> tuple[str | None, float]:
    normalized = {h.strip().lower() for h in headers}
    best_name, best_score = None, 0.0
    for signature, provider in KNOWN_SIGNATURES:
        score = len(signature & normalized) / len(signature)
        if score > best_score:
            best_name, best_score = provider, score
    return (best_name, best_score) if best_score >= 0.65 else (None, best_score)


def parse_amount(value: str | None) -> Decimal:
    cleaned = (value or "").strip().replace(",", "").replace("$", "")
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("() ") or "0"
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid amount: {value}") from exc
    return -amount if negative else amount


def can_parse_amount(value: str) -> bool:
    try:
        parse_amount(value)
        return bool(value.strip())
    except ValueError:
        return False


def parse_date(value: str | None) -> date:
    if not value or not value.strip():
        raise ValueError("Missing transaction date")
    return date_parser.parse(value, fuzzy=False).date()


def normalize_card_identifier(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    raw = value.strip()
    digits = re.sub(r"\D", "", raw)
    last_four = digits[-4:] if len(digits) >= 4 else None
    masked = f"xxxx{last_four}" if last_four else raw[:64]
    return masked, last_four


def clean_description(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
