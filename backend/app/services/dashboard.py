from decimal import Decimal


def summary_payload(start, end, spending, income, recurring, uncategorized, review_needed):
    spending = Decimal(spending or 0)
    income = Decimal(income or 0)
    return {
        "start_date": start,
        "end_date": end,
        "spending": spending,
        "income": income,
        "net_cash_flow": income - spending,
        "recurring_spend": Decimal(recurring or 0),
        "uncategorized_count": int(uncategorized or 0),
        "review_needed_count": int(review_needed or 0),
    }

