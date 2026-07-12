from datetime import date
from decimal import Decimal

from app.models import Cadence
from app.services.dashboard import summary_payload
from app.services.recurring import cadence_for_days, next_date


def test_recurring_cadence_detection():
    assert cadence_for_days(30) == Cadence.monthly
    assert cadence_for_days(7) == Cadence.weekly
    assert cadence_for_days(18) is None


def test_monthly_next_date_handles_end_of_month():
    assert next_date(date(2026, 1, 31), Cadence.monthly) == date(2026, 2, 28)


def test_dashboard_summary_uses_income_minus_spending():
    result = summary_payload(date(2026, 7, 1), date(2026, 7, 31), "850.25", "3000", "42", 3, 9)
    assert result["net_cash_flow"] == Decimal("2149.75")
    assert result["recurring_spend"] == Decimal("42")
    assert result["uncategorized_count"] == 3


# Provider-category mapping is exercised during normalize_import once a database-backed
# import fixture is available. Place real provider CSV exports under tests/fixtures/local/;
# that directory should remain uncommitted because bank files may contain sensitive data.

