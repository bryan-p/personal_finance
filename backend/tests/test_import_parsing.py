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
    resolve_header_name,
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


def test_chase_mapping_keeps_category_and_provider_type_separate():
    headers = [
        "Transaction Date",
        "Post Date",
        "Description",
        "Category",
        "Type",
        "Amount",
        "Memo",
    ]
    rows = [{
        "Transaction Date": "02/25/2026",
        "Post Date": "02/26/2026",
        "Description": "sandals r us",
        "Category": "Shopping",
        "Type": "Sale",
        "Amount": "-16.99",
        "Memo": "",
    }]

    mapping = detect_mapping(headers, rows)

    assert mapping["description_column"] == "Description"
    assert mapping["category_column"] == "Category"
    assert mapping["provider_type_column"] == "Type"
    assert mapping["memo_column"] == "Memo"
    assigned = [
        value
        for key, value in mapping.items()
        if key.endswith("_column")
    ]
    assert len(assigned) == len(set(assigned))


def test_mapping_keeps_alternate_description_and_status_as_source_fields():
    headers = ["Date", "Description", "Original Description", "Status", "Amount"]
    rows = [{
        "Date": "07/01/2026",
        "Description": "COFFEE SHOP",
        "Original Description": "CARD PURCHASE COFFEE SHOP 1234",
        "Status": "Posted",
        "Amount": "-5.25",
    }]

    mapping = detect_mapping(headers, rows)

    assert mapping["description_column"] == "Description"
    assert mapping["memo_column"] == "Original Description"
    assert mapping["status_column"] == "Status"


def test_single_memo_header_is_used_as_required_description():
    mapping = detect_mapping(
        ["Date", "Memo", "Amount"],
        [{"Date": "07/01/2026", "Memo": "Lunch", "Amount": "12.50"}],
    )

    assert mapping["description_column"] == "Memo"
    assert "memo_column" not in mapping


def test_unknown_provider_gets_generic_mapping():
    headers = ["Activity day", "Memo text", "Value USD"]
    rows = [{"Activity day": "2026-07-01", "Memo text": "Lunch", "Value USD": "12.50"}]
    mapping = detect_mapping(headers, rows)
    assert mapping["description_column"] == "Memo text"
    assert mapping["amount_column"] == "Value USD"
    assert mapping["confidence"]["amount_column"] == 0.45


def test_header_signature_ignores_order_and_case():
    assert header_signature(["Date", "Amount"]) == header_signature([" amount ", "DATE"])
    assert resolve_header_name("Transaction Date", ["transaction date", "Amount"]) == "transaction date"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("$1,234.50", Decimal("1234.50")), ("(42.10)", Decimal("-42.10")), ("-7", Decimal("-7"))],
)
def test_amount_parsing(raw, expected):
    assert parse_amount(raw) == expected


def test_date_and_safe_card_identifier_normalization():
    assert parse_date("07/04/2026").isoformat() == "2026-07-04"
    assert normalize_card_identifier("4111-1111-1111-9876") == ("xxxx9876", "9876")
