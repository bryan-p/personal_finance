from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import MappingIn


def test_import_mapping_rejects_reusing_a_csv_column():
    with pytest.raises(ValidationError, match="Each CSV column can only be mapped"):
        MappingIn(
            institution_id=uuid4(),
            account_type="credit_card",
            mapping_name="Duplicate mapping",
            date_column="Date",
            description_column="Description",
            category_column="Type",
            provider_type_column="Type",
            amount_column="Amount",
            amount_behavior="signed_amount",
        )
