from app.services.institutions import (
    STARTER_INSTITUTIONS,
    clean_institution_name,
    normalize_institution_name,
)


def test_institution_name_normalization_is_case_and_whitespace_insensitive():
    assert clean_institution_name("  American   Express  ") == "American Express"
    assert normalize_institution_name("  AMERICAN   EXPRESS  ") == "american express"


def test_starter_institutions_include_major_banks_and_card_issuers():
    expected = {
        "American Express",
        "Bank of America",
        "Capital One",
        "Chase",
        "Citi",
        "Discover",
        "Wells Fargo",
    }
    assert expected <= set(STARTER_INSTITUTIONS)
