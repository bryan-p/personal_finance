# Rule-Definition Popup on Import Review + Rule Editing on Rules Page

## Problem

1. On the import review page (`frontend/src/app/(app)/imports/[id]/review/page.tsx`), the "Rule from edit" button creates a rule via a bare `window.confirm()` with hard-coded criteria (first ≥4-char token of the description, `description contains`). The user cannot adjust the match criteria, name, priority, category, or subcategory before the rule is created.
2. On the rules page (`frontend/src/app/(app)/rules/page.tsx`), rules can only be created and toggled active/inactive. There is no way to edit an existing rule, even though the backend `PATCH /rules/{rule_id}` + `RulePatch` schema fully support it. The create form also lacks subcategory selection despite backend support.

## Solution

Build a shared, reusable `RuleForm` modal component used in two places:

- **Import review**: the "Rule from edit" button opens the modal prefilled from the selected draft row instead of calling `window.confirm()`.
- **Rules page**: an "Edit" action per rule opens the same modal prefilled from the existing rule and saves via `PATCH /rules/{rule_id}`. The existing create modal is replaced by the shared form in create mode.

Add light backend validation so rules can't reference another user's category/subcategory or a subcategory that doesn't belong to the selected category.

## Requirements

### Shared RuleForm component (`frontend/src/components/RuleForm.tsx` or similar)

- Modal styling consistent with existing modals in the app (hand-written `globals.css`, no CSS framework).
- Fields: name, priority, is_active, match_field (all 10 backend values), match_operator (all 6), match_value, category (filtered to `is_active`), subcategory (dependent on selected category, filtered to `is_active`), transaction_type, is_excluded_from_spending, mark_as_recurring, merchant_name_override, note.
- Subcategory selector: disabled/empty until a category is chosen; options come from the selected category's nested `subcategories` (from `GET /categories`); resets when category changes.
- Modes: `create` (POST /rules) and `edit` (PATCH /rules/{id}). In edit mode, send the full field set (explicit `null` for cleared optional actions so PATCH actually clears them).
- Move the `Rule` interface into `frontend/src/lib/types.ts` (include `note`) and use it in both pages.
- Success/error feedback consistent with existing patterns; disable submit while in flight to prevent duplicate rules.

### Import review integration

- "Rule from edit" opens the modal prefilled: name `Categorize <token>`, priority 100, match_field `description`, operator `contains`, match_value derived as today BUT from `description_original` (rules match `description_original`, not `description_clean` — deriving from the clean text can create rules that never match), category_id/subcategory_id from the row, merchant_name_override from the row.
- On successful create, close the modal and show existing-style feedback. Do NOT re-run normalization or auto-apply the rule to other drafts (re-normalizing deletes drafts and loses review edits — out of scope).
- Keep the current button visibility condition.

### Rules page integration

- Each rule row gets an "Edit" button opening the shared form in edit mode, prefilled from the rule.
- Rule list display: show subcategory alongside category, and the configured actions.
- Keep the existing enable/disable toggle.

### Backend validation (`backend/app/api/rules.py`)

- On create and update: if `category_id` is set, verify it belongs to the current user (404/422 otherwise). If `subcategory_id` is set, verify it belongs to the current user AND to the resolved category (the payload's category if provided, else the rule's existing category on PATCH). Reject subcategory with no category.
- Follow the existing error-response patterns in the codebase.

## Out of Scope

- Applying new/edited rules retroactively to existing drafts or confirmed transactions.
- Rule delete/test UI (backend endpoints exist; not requested).
- Changing matching semantics.

## Files to Modify

- `frontend/src/components/RuleForm.tsx` — new shared modal form
- `frontend/src/lib/types.ts` — shared `Rule` type
- `frontend/src/app/(app)/imports/[id]/review/page.tsx` — replace confirm() flow with modal
- `frontend/src/app/(app)/rules/page.tsx` — edit mode, subcategory display, use shared form
- `backend/app/api/rules.py` — ownership/consistency validation on create + patch
- `frontend/src/app/globals.css` — only if modal styles need additions

## Success Criteria

- From import review, clicking "Rule from edit" opens a popup where criteria, category, and subcategory can be adjusted before saving; saving creates the rule.
- On /rules, an existing rule can be fully edited (including clearing optional fields) and the changes persist.
- Frontend typechecks/builds cleanly; backend rejects cross-user or mismatched category/subcategory references.
