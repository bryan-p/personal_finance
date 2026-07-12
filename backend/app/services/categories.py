from sqlalchemy.orm import Session

from app.models import Category, Subcategory


STARTER_CATEGORIES = {
    "Income": ["Paycheck", "Interest", "Refund", "Other Income"],
    "Housing": ["Rent", "Mortgage", "HOA", "Repairs", "Furniture"],
    "Food": ["Groceries", "Restaurants", "Coffee", "Delivery"],
    "Transportation": ["Gas", "Parking", "Public Transit", "Rideshare", "Maintenance"],
    "Utilities": ["Electric", "Gas", "Water", "Internet", "Phone"],
    "Insurance": ["Auto Insurance", "Health Insurance", "Home Insurance", "Life Insurance"],
    "Healthcare": ["Doctor", "Pharmacy", "Dental", "Vision"],
    "Shopping": ["General Shopping", "Clothing", "Electronics", "Household"],
    "Entertainment": ["Movies", "Events", "Games", "Hobbies"],
    "Travel": ["Flights", "Hotels", "Rental Cars", "Travel Food"],
    "Subscriptions": ["Streaming", "Software", "Memberships", "News", "Cloud Storage"],
    "Fees": ["Bank Fees", "Credit Card Fees", "ATM Fees", "Late Fees"],
    "Taxes": ["Federal Taxes", "State Taxes", "Local Taxes", "Tax Prep"],
    "Transfers": ["Bank Transfer", "Internal Transfer", "Zelle", "Venmo", "PayPal"],
    "Credit Card Payments": ["Credit Card Payment"],
    "Other": ["Uncategorized", "Miscellaneous"],
}


def seed_categories(db: Session, user_id):
    for position, (name, children) in enumerate(STARTER_CATEGORIES.items()):
        category = Category(user_id=user_id, name=name, is_system=True, sort_order=position)
        db.add(category)
        db.flush()
        for child_position, child in enumerate(children):
            db.add(
                Subcategory(
                    user_id=user_id,
                    category_id=category.id,
                    name=child,
                    is_system=True,
                    sort_order=child_position,
                )
            )

