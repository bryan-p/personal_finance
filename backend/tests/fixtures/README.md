# CSV fixtures

Automated tests use small synthetic CSV strings so the repository never contains real
financial data. Put sanitized provider samples in `backend/tests/fixtures/local/` when
developing a provider-specific parser. That directory is ignored by Git.

A useful sanitized fixture keeps the original headers and replaces every row with fake
dates, descriptions, identifiers, card suffixes, and amounts. Generic CSV formats should
normally be added through the mapping UI instead of receiving a provider-specific parser.

