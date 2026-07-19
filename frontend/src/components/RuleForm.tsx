"use client";

import { FormEvent, useState } from "react";
import { X } from "lucide-react";
import { api } from "@/lib/api";
import type { Category, Rule, RuleMatchField, RuleMatchOperator } from "@/lib/types";

const matchFields: RuleMatchField[] = [
  "description",
  "merchant",
  "account",
  "account_instrument",
  "source_category",
  "source_transaction_type",
  "amount",
  "direction",
  "cardholder_name",
  "card_last_four",
];

const matchOperators: RuleMatchOperator[] = [
  "contains",
  "equals",
  "starts_with",
  "regex",
  "greater_than",
  "less_than",
];

const transactionTypes = ["expense", "income", "transfer", "credit_card_payment", "refund", "fee", "adjustment", "other"];

type OptionalBoolean = "" | "true" | "false";

interface RuleFormState {
  name: string;
  priority: string;
  is_active: boolean;
  match_field: RuleMatchField;
  match_operator: RuleMatchOperator;
  match_value: string;
  category_id: string;
  subcategory_id: string;
  transaction_type: string;
  is_excluded_from_spending: OptionalBoolean;
  mark_as_recurring: OptionalBoolean;
  merchant_name_override: string;
  note: string;
}

interface RuleFormProps {
  categories: Category[];
  mode: "create" | "edit";
  rule?: Rule;
  initialValues?: Partial<Rule>;
  onClose: () => void;
  onSuccess: (rule: Rule) => void;
}

function label(value: string) {
  return value.replaceAll("_", " ");
}

function optionalBoolean(value: boolean | null | undefined): OptionalBoolean {
  if (value === true) return "true";
  if (value === false) return "false";
  return "";
}

function booleanPayload(value: OptionalBoolean) {
  if (!value) return null;
  return value === "true";
}

export function RuleForm({ categories, mode, rule, initialValues, onClose, onSuccess }: RuleFormProps) {
  const source = rule || initialValues || {};
  const activeCategories = categories.filter((category) => category.is_active);
  const initialCategory = categories.find((category) => category.id === source.category_id);
  const initialSubcategory = initialCategory?.subcategories.find(
    (subcategory) => subcategory.id === source.subcategory_id,
  );
  const assignedCategory = mode === "edit" ? initialCategory : undefined;
  const assignedSubcategory = mode === "edit" ? initialSubcategory : undefined;
  const categoryOptions = assignedCategory && !assignedCategory.is_active
    ? [...activeCategories, assignedCategory]
    : activeCategories;
  const [values, setValues] = useState<RuleFormState>({
    name: source.name || "",
    priority: String(source.priority ?? 100),
    is_active: source.is_active ?? true,
    match_field: source.match_field || "description",
    match_operator: source.match_operator || "contains",
    match_value: source.match_value || "",
    category_id: mode === "edit"
      ? source.category_id || ""
      : initialCategory?.is_active ? initialCategory.id : "",
    subcategory_id: mode === "edit"
      ? source.subcategory_id || ""
      : initialCategory?.is_active && initialSubcategory?.is_active ? initialSubcategory.id : "",
    transaction_type: source.transaction_type || "",
    is_excluded_from_spending: optionalBoolean(source.is_excluded_from_spending),
    mark_as_recurring: optionalBoolean(source.mark_as_recurring),
    merchant_name_override: source.merchant_name_override || "",
    note: source.note || "",
  });
  const [error, setError] = useState("");
  const [matchValueError, setMatchValueError] = useState("");
  const [saving, setSaving] = useState(false);

  const selectedCategory = categories.find((category) => category.id === values.category_id);
  const activeSubcategories = selectedCategory?.subcategories.filter((subcategory) => subcategory.is_active) || [];
  const showAssignedInactiveSubcategory = assignedSubcategory
    && !assignedSubcategory.is_active
    && values.category_id === assignedCategory?.id;
  const subcategoryOptions = showAssignedInactiveSubcategory
    ? [...activeSubcategories, assignedSubcategory]
    : activeSubcategories;

  function update<K extends keyof RuleFormState>(key: K, value: RuleFormState[K]) {
    if (key === "match_value") setMatchValueError("");
    setValues((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    if (mode === "edit" && !rule) {
      setError("Could not identify the rule to edit");
      return;
    }
    const matchValue = values.match_value.trim();
    if (!matchValue) {
      setMatchValueError("Enter a non-blank match value");
      return;
    }

    setSaving(true);
    setError("");
    setMatchValueError("");
    const payload = {
      name: values.name,
      priority: Number(values.priority),
      is_active: values.is_active,
      match_field: values.match_field,
      match_operator: values.match_operator,
      match_value: matchValue,
      category_id: values.category_id || null,
      subcategory_id: values.subcategory_id || null,
      transaction_type: values.transaction_type || null,
      is_excluded_from_spending: booleanPayload(values.is_excluded_from_spending),
      mark_as_recurring: booleanPayload(values.mark_as_recurring),
      merchant_name_override: values.merchant_name_override || null,
      note: values.note || null,
    };

    try {
      const saved = await api<Rule>(mode === "edit" ? `/rules/${rule!.id}` : "/rules", {
        method: mode === "edit" ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });
      onSuccess(saved);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save rule");
    } finally {
      setSaving(false);
    }
  }

  return <div className="modal-backdrop">
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="rule-form-title">
      <div className="modal-header">
        <h2 id="rule-form-title">{mode === "edit" ? "Edit categorization rule" : "Create categorization rule"}</h2>
        <button className="icon-button" type="button" onClick={onClose} disabled={saving} aria-label="Close rule form"><X/></button>
      </div>
      {error && <div className="notice notice-error">{error}</div>}
      <form onSubmit={submit}>
        <div className="form-grid">
          <div className="field full">
            <label>Rule name</label>
            <input className="input" value={values.name} onChange={(event) => update("name", event.target.value)} required maxLength={160} placeholder="Netflix subscription"/>
          </div>
          <div className="field">
            <label>Priority (lower runs first)</label>
            <input className="input" type="number" min={0} max={2147483647} value={values.priority} onChange={(event) => update("priority", event.target.value)} required/>
          </div>
          <div className="field">
            <label>Rule status</label>
            <label className="inline-check"><input type="checkbox" checked={values.is_active} onChange={(event) => update("is_active", event.target.checked)}/> Active</label>
          </div>
          <div className="field">
            <label>Match field</label>
            <select className="select" value={values.match_field} onChange={(event) => update("match_field", event.target.value as RuleMatchField)}>
              {matchFields.map((field) => <option key={field} value={field}>{label(field)}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Operator</label>
            <select className="select" value={values.match_operator} onChange={(event) => update("match_operator", event.target.value as RuleMatchOperator)}>
              {matchOperators.map((operator) => <option key={operator} value={operator}>{label(operator)}</option>)}
            </select>
          </div>
          <div className="field full">
            <label>Match value</label>
            <input
              className="input"
              value={values.match_value}
              onChange={(event) => update("match_value", event.target.value)}
              aria-invalid={Boolean(matchValueError)}
              aria-describedby={matchValueError ? "match-value-error" : undefined}
              aria-required="true"
              maxLength={500}
              placeholder="NETFLIX"
            />
            {matchValueError && <span className="field-error" id="match-value-error" role="alert">{matchValueError}</span>}
          </div>
          <div className="field">
            <label>Set category</label>
            <select className="select" value={values.category_id} onChange={(event) => setValues((current) => ({ ...current, category_id: event.target.value, subcategory_id: "" }))}>
              <option value="">No change</option>
              {categoryOptions.map((category) => <option key={category.id} value={category.id} disabled={!category.is_active}>
                {category.name}{category.is_active ? "" : " (inactive)"}
              </option>)}
            </select>
          </div>
          <div className="field">
            <label>Set subcategory</label>
            <select className="select" value={values.subcategory_id} onChange={(event) => update("subcategory_id", event.target.value)} disabled={!values.category_id}>
              <option value="">No subcategory</option>
              {subcategoryOptions.map((subcategory) => <option key={subcategory.id} value={subcategory.id} disabled={!subcategory.is_active}>
                {subcategory.name}{subcategory.is_active ? "" : " (inactive)"}
              </option>)}
            </select>
          </div>
          <div className="field">
            <label>Set transaction type</label>
            <select className="select" value={values.transaction_type} onChange={(event) => update("transaction_type", event.target.value)}>
              <option value="">No change</option>
              {transactionTypes.map((type) => <option key={type} value={type}>{label(type)}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Spending action</label>
            <select className="select" value={values.is_excluded_from_spending} onChange={(event) => update("is_excluded_from_spending", event.target.value as OptionalBoolean)}>
              <option value="">No change</option>
              <option value="true">Exclude from spending</option>
              <option value="false">Include in spending</option>
            </select>
          </div>
          <div className="field">
            <label>Recurring action</label>
            <select className="select" value={values.mark_as_recurring} onChange={(event) => update("mark_as_recurring", event.target.value as OptionalBoolean)}>
              <option value="">No change</option>
              <option value="true">Mark recurring</option>
              <option value="false">Mark not recurring</option>
            </select>
          </div>
          <div className="field">
            <label>Merchant name override</label>
            <input className="input" value={values.merchant_name_override} onChange={(event) => update("merchant_name_override", event.target.value)} maxLength={255}/>
          </div>
          <div className="field full">
            <label>Note</label>
            <textarea className="textarea" value={values.note} onChange={(event) => update("note", event.target.value)}/>
          </div>
        </div>
        <div className="form-actions">
          <button type="button" className="button" onClick={onClose} disabled={saving}>Cancel</button>
          <button className="button button-primary" disabled={saving}>{saving ? "Saving…" : mode === "edit" ? "Save changes" : "Create rule"}</button>
        </div>
      </form>
    </div>
  </div>;
}
