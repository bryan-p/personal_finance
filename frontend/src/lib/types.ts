export type AccountType = "checking" | "savings" | "credit_card" | "cash" | "other";

export interface Institution {
  id: string;
  display_name: string;
  normalized_name: string;
  is_system: boolean;
  is_active: boolean;
}

export interface Account {
  id: string;
  name: string;
  institution_id?: string;
  institution?: Institution;
  account_type: AccountType;
  last_four?: string;
  currency: string;
  is_active: boolean;
  statement_cycle_day?: number;
  payment_due_day?: number;
}

export interface AccountDeletionImpact {
  account_id: string;
  account_name: string;
  transaction_count: number;
  draft_transaction_count: number;
  instrument_count: number;
  import_count: number;
  upload_file_count: number;
  deleted_file_count?: number;
}

export interface Instrument {
  id: string;
  account_id: string;
  instrument_type: string;
  display_name: string;
  cardholder_name?: string;
  last_four?: string;
  source_identifier?: string;
  is_active: boolean;
}

export interface Subcategory { id: string; category_id: string; name: string; is_active: boolean; }
export interface Category { id: string; name: string; description?: string; is_active: boolean; is_system: boolean; subcategories: Subcategory[]; }

export interface ImportRecord {
  id: string; account_id: string; original_filename: string; institution_id?: string; institution_name?: string; account_type?: AccountType; status: string;
  row_count: number; duplicate_row_count: number; imported_row_count: number; is_duplicate_file: boolean;
  error_message?: string;
  created_at: string; headers?: string[]; sample_rows?: Record<string, string>[]; proposed_mapping?: Record<string, unknown>;
  header_signature?: string;
}

export interface DraftTransaction {
  id: string; transaction_date: string; posted_date?: string; description_clean: string; merchant_name?: string;
  amount: string; direction: string; transaction_type: string; source_transaction_type?: string; category_id?: string; subcategory_id?: string;
  account_instrument_id?: string; card_last_four?: string; cardholder_name?: string; is_excluded_from_spending: boolean;
  is_recurring: boolean; recurring_candidate: boolean; duplicate_status: string; review_status: string; rule_applied: boolean; notes?: string;
}

export interface Transaction extends Omit<DraftTransaction, "rule_applied" | "recurring_candidate" | "duplicate_status" | "review_status"> {
  account_id: string; source_category?: string;
}
