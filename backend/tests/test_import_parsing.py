from decimal import Decimal

import pytest

from app.services.imports.parsing import (
    detect_mapping,
    detect_provider,
    header_signature,
    normalize_card_identifier,
    parse_amount,
    parse_csv,
    parse_date,
)


def test_csv_header_parsing_handles_bom_and_rows():
    content = "\ufeffDate,Description,Amount\n01/02/2026,Coffee,-4.50\n".encode()
    headers, rows = parse_csv(content)
    assert headers == ["Date", "Description", "Amount"]
    assert rows[0]["Description"] == "Coffee"


def test_known_provider_detection():
    provider, confidence = detect_provider(["Transaction Date", "Post Date", "Description", "Category", "Type", "Amount"])
    assert provider == "Chase"
    assert confidence == 1


def test_unknown_provider_gets_generic_mapping():
    headers = ["Activity day", "Memo text", "Value USD"]
    rows = [{"Activity day": "2026-07-01", "Memo text": "Lunch", "Value USD": "12.50"}]
    mapping = detect_mapping(headers, rows)
    assert mapping["description_column"] == "Memo text"
    assert mapping["amount_column"] == "Value USD"
    assert mapping["confidence"]["amount_column"] == 0.45


def test_header_signature_ignores_order_and_case():
    assert header_signature(["Date", "Amount"]) == header_signature([" amount ", "DATE"])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("$1,234.50", Decimal("1234.50")), ("(42.10)", Decimal("-42.10")), ("-7", Decimal("-7"))],
)
def test_amount_parsing(raw, expected):
    assert parse_amount(raw) == expected


def test_date_and_safe_card_identifier_normalization():
    assert parse_date("07/04/2026").isoformat() == "2026-07-04"
    assert normalize_card_identifier("4111-1111-1111-9876") == ("xxxx9876", "9876")

