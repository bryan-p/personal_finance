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
    "merchant_column": ["merchant", "payee"],
    "amount_column": ["amount", "transaction amount"],
    "debit_column": ["debit", "withdrawal", "charge"],
    "credit_column": ["credit", "deposit", "payment"],
    "category_column": ["category", "type"],
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


def header_signature(headers: list[str]) -> str:
    normalized = "|".join(sorted(re.sub(r"\s+", " ", header.strip().lower()) for header in headers))
    return hashlib.sha256(normalized.encode()).hexdigest()


def file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _score_header(header: str, aliases: list[str]) -> float:
    normalized = re.sub(r"[_-]+", " ", header.strip().lower())
    if normalized in aliases:
        return 1.0
    if any(alias in normalized or normalized in alias for alias in aliases):
        return 0.75
    return 0.0


def detect_mapping(headers: list[str], sample_rows: list[dict]) -> dict:
    detected: dict[str, str | float] = {}
    confidence: dict[str, float] = {}
    for field, aliases in HEADER_ALIASES.items():
        matches = sorted(((_score_header(h, aliases), h) for h in headers), reverse=True)
        if matches and matches[0][0] > 0:
            detected[field] = matches[0][1]
            confidence[field] = matches[0][0]
    if "amount_column" not in detected and not ({"debit_column", "credit_column"} <= detected.keys()):
        for header in headers:
            values = [row.get(header, "") for row in sample_rows[:10]]
            if values and sum(can_parse_amount(v) for v in values) / len(values) >= 0.8:
                detected["amount_column"] = header
                confidence["amount_column"] = 0.45
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

