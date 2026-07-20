"use client";

import { Trash2, X } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Badge, EmptyState, PageHeader } from "@/components/Page";
import { RuleForm } from "@/components/RuleForm";
import { api, money, shortDate } from "@/lib/api";
import { impliedTransactionType, soleActiveSubcategoryId } from "@/lib/categories";
import type { Category, DraftTransaction, ImportRecord, Instrument, Rule, Subcategory } from "@/lib/types";

const types = ["expense", "income", "transfer", "credit_card_payment", "refund", "fee", "adjustment", "other"];
const ADD_CATEGORY_VALUE = "__add_category__";
const ADD_SUBCATEGORY_VALUE = "__add_subcategory__";

type TaxonomyModal =
  | { kind: "category"; rowId: string }
  | { kind: "subcategory"; rowId: string; categoryId: string };

interface ApplyRuleResult {
  matched: number;
  updated: number;
  skipped_reviewed: number;
  drafts: DraftTransaction[];
}

function willImport(row: DraftTransaction) {
  return row.review_status !== "skipped"
    && (row.duplicate_status !== "duplicate" || row.review_status === "approved");
}

function isExcludedDuplicate(row: DraftTransaction) {
  return row.duplicate_status === "duplicate" && !willImport(row);
}

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [rows, setRows] = useState<DraftTransaction[]>([]);
  const [item, setItem] = useState<ImportRecord | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [ruleDefaults, setRuleDefaults] = useState<Partial<Rule> | null>(null);
  const [taxonomyModal, setTaxonomyModal] = useState<TaxonomyModal | null>(null);
  const [taxonomyError, setTaxonomyError] = useState("");
  const [taxonomySaving, setTaxonomySaving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [filter, setFilter] = useState("");

  async function load() {
    try {
      const [drafts, info, cats] = await Promise.all([
        api<DraftTransaction[]>(`/imports/${id}/review`),
        api<ImportRecord>(`/imports/${id}`),
        api<Category[]>("/categories"),
      ]);
      setRows(drafts);
      setItem(info);
      setCategories(cats);
      setSelected(new Set());
      setInstruments(await api<Instrument[]>(`/accounts/${info.account_id}/instruments`));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load review");
    }
  }

  useEffect(() => { load(); }, [id]);
  useEffect(() => { setSelected(new Set()); }, [filter]);

  async function change(row: DraftTransaction, changes: Record<string, unknown>) {
    const nextReviewStatus = typeof changes.review_status === "string" ? changes.review_status : "edited";
    setRows((current) => current.map((candidate) => candidate.id === row.id
      ? { ...candidate, ...changes, review_status: nextReviewStatus } as DraftTransaction
      : candidate));
    try {
      const saved = await api<DraftTransaction>(`/imports/${id}/draft-transactions/${row.id}`, {
        method: "PATCH",
        body: JSON.stringify(changes),
      });
      setRows((current) => current.map((candidate) => candidate.id === row.id
        ? { ...candidate, ...saved }
        : candidate));
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save edit");
      await load();
      return false;
    }
  }

  function createRule(row: DraftTransaction) {
    const token = row.description_original.split(/\s+/).find((part) => part.length >= 4) || row.description_original;
    setError("");
    setFeedback("");
    setRuleDefaults({
      name: `Categorize ${token}`,
      priority: 100,
      is_active: true,
      match_field: "description",
      match_operator: "contains",
      match_value: token,
      category_id: row.category_id || null,
      subcategory_id: row.subcategory_id || null,
      merchant_name_override: row.merchant_name || null,
    });
  }

  async function applyCreatedRule(rule: Rule) {
    setRuleDefaults(null);
    setError("");
    if (!rule.is_active) {
      setFeedback("Rule created (inactive — not applied).");
      return;
    }
    try {
      const result = await api<ApplyRuleResult>(`/imports/${id}/draft-transactions/apply-rule`, {
        method: "POST",
        body: JSON.stringify({ rule_id: rule.id }),
      });
      const updatedById = new Map(result.drafts.map((draft) => [draft.id, draft]));
      setRows((current) => current.map((row) => updatedById.get(row.id) || row));
      setFeedback(`Rule created — applied to ${result.updated} other transaction${result.updated === 1 ? "" : "s"} on this import.`);
    } catch (reason) {
      setFeedback(`Rule “${rule.name}” created. It will apply to future normalizations.`);
      setError(reason instanceof Error ? `Rule was created, but could not be applied to this import: ${reason.message}` : "Rule was created, but could not be applied to this import");
    }
  }

  function openTaxonomyModal(modal: TaxonomyModal) {
    setTaxonomyError("");
    setTaxonomyModal(modal);
  }

  function closeTaxonomyModal() {
    setTaxonomyError("");
    setTaxonomyModal(null);
  }

  async function createTaxonomyItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!taxonomyModal) return;

    const row = rows.find((candidate) => candidate.id === taxonomyModal.rowId);
    if (!row) {
      setTaxonomyError("This draft transaction is no longer available");
      return;
    }

    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") || "");
    const description = String(form.get("description") || "") || null;
    setTaxonomySaving(true);
    setTaxonomyError("");
    try {
      if (taxonomyModal.kind === "category") {
        const created = await api<Category>("/categories", {
          method: "POST",
          body: JSON.stringify({ name, description }),
        });
        setCategories((current) => [...current, created]);
        const assigned = await change(row, { category_id: created.id, subcategory_id: null });
        closeTaxonomyModal();
        setFeedback(assigned
          ? `Category “${created.name}” created and assigned.`
          : `Category “${created.name}” was created, but could not be assigned to this row.`);
      } else {
        const created = await api<Subcategory>("/subcategories", {
          method: "POST",
          body: JSON.stringify({
            category_id: taxonomyModal.categoryId,
            name,
            description,
          }),
        });
        setCategories((current) => current.map((category) => category.id === taxonomyModal.categoryId
          ? { ...category, subcategories: [...category.subcategories, created] }
          : category));
        const assigned = await change(row, { subcategory_id: created.id });
        closeTaxonomyModal();
        setFeedback(assigned
          ? `Subcategory “${created.name}” created and assigned.`
          : `Subcategory “${created.name}” was created, but could not be assigned to this row.`);
      }
    } catch (reason) {
      setTaxonomyError(reason instanceof Error ? reason.message : "Could not create category");
    } finally {
      setTaxonomySaving(false);
    }
  }

  async function confirm() {
    setConfirming(true);
    try {
      await api(`/imports/${id}/confirm`, { method: "POST" });
      router.push("/transactions");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not confirm");
      setConfirming(false);
    }
  }

  async function deleteDrafts(ids: string[]) {
    const label = ids.length === 1 ? "this draft transaction" : `${ids.length} draft transactions`;
    if (!window.confirm(`Permanently delete ${label}? Deleted rows will not be imported.`)) return;
    setDeleting(true);
    try {
      if (ids.length === 1) {
        await api(`/imports/${id}/draft-transactions/${ids[0]}`, { method: "DELETE" });
      } else {
        await api(`/imports/${id}/bulk-delete`, {
          method: "POST",
          body: JSON.stringify({ ids }),
        });
      }
      const deleted = new Set(ids);
      setRows((current) => current.filter((row) => !deleted.has(row.id)));
      setSelected((current) => new Set([...current].filter((rowId) => !deleted.has(rowId))));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete draft transactions");
      await load();
    } finally {
      setDeleting(false);
    }
  }

  function toggle(rowId: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  }

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(displayedRows.map((row) => row.id)));
  }

  const counts = useMemo(() => ({
    willImport: rows.filter(willImport).length,
    skipped: rows.filter((row) => row.review_status === "skipped").length,
    duplicateExcluded: rows.filter((row) => row.duplicate_status === "duplicate" && row.review_status !== "approved" && row.review_status !== "skipped").length,
    duplicateIncluded: rows.filter((row) => row.duplicate_status === "duplicate" && row.review_status === "approved").length,
    uncategorized: rows.filter((row) => willImport(row) && !row.category_id).length,
    rules: rows.filter((row) => row.rule_applied).length,
  }), [rows]);
  const displayedRows = useMemo(
    () => filter ? rows.filter((row) => row.account_instrument_id === filter) : rows,
    [filter, rows],
  );
  const allSelected = displayedRows.length > 0 && displayedRows.every((row) => selected.has(row.id));
  const importLabel = `${counts.willImport} transaction${counts.willImport === 1 ? "" : "s"}`;
  const modalCategory = taxonomyModal?.kind === "subcategory"
    ? categories.find((category) => category.id === taxonomyModal.categoryId)
    : null;

  return <>
    <div className="steps"><div className="step done"/><div className="step done"/><div className="step active"/></div>
    <PageHeader
      eyebrow="Step 3 of 3"
      title="Review draft transactions"
      description={`${item?.original_filename || "CSV"} · ${rows.length} rows. Edits save immediately, so you can safely return later.`}
      actions={<>
        <button className="button" onClick={() => router.push("/imports")}>Resume later</button>
        <button className="button button-primary" onClick={confirm} disabled={confirming || deleting}>{confirming ? "Importing…" : `Confirm ${importLabel}`}</button>
      </>}
    />
    {error && <div className="notice notice-error">{error}</div>}
    {feedback && <div className="notice notice-good">{feedback}</div>}
    <div className="toolbar">
      <Badge tone="good">{importLabel} will import</Badge>
      <Badge tone={counts.skipped ? "warn" : "good"}>{counts.skipped} skipped</Badge>
      <Badge tone={counts.duplicateExcluded ? "danger" : "good"}>{counts.duplicateExcluded} duplicates excluded</Badge>
      {counts.duplicateIncluded > 0 && <Badge tone="warn">{counts.duplicateIncluded} duplicates included</Badge>}
      <Badge tone={counts.uncategorized ? "warn" : "good"}>{counts.uncategorized} uncategorized</Badge>
      <Badge tone="accent">{counts.rules} rule-applied</Badge>
      {selected.size > 0 && <div className="selection-actions">
        <strong>{selected.size} selected</strong>
        <button className="button button-danger" onClick={() => deleteDrafts([...selected])} disabled={deleting}><Trash2 size={15}/>{deleting ? "Deleting…" : "Delete selected"}</button>
      </div>}
      <div className="field" style={{ marginLeft: "auto" }}>
        <label>Card/profile</label>
        <select className="select" value={filter} onChange={(event) => setFilter(event.target.value)}>
          <option value="">All profiles</option>
          {instruments.map((instrument) => <option key={instrument.id} value={instrument.id}>{instrument.display_name}</option>)}
        </select>
      </div>
    </div>
    <div className="card table-card">
      {!displayedRows.length ? <EmptyState title="No draft rows" body="Normalize the import mapping first, or clear the active card/profile filter."/> : <div className="table-scroll">
        <table className="data-table">
          <thead><tr>
            <th className="selection-cell"><input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="Select all displayed draft transactions"/></th>
            <th>Flags</th><th>Date</th><th>Description</th><th>Amount</th><th>Category</th><th>Type</th><th>Card/profile</th><th>Excluded</th><th>Recurring</th><th>Skip</th><th>Actions</th>
          </tr></thead>
          <tbody>{displayedRows.map((row) => {
            const category = categories.find((candidate) => candidate.id === row.category_id);
            const rowClasses = [
              row.is_excluded_from_spending && "excluded-row",
              row.review_status === "skipped" && "skipped-row",
              isExcludedDuplicate(row) && "duplicate-excluded-row",
            ].filter(Boolean).join(" ");
            return <tr key={row.id} className={rowClasses}>
              <td className="selection-cell"><input type="checkbox" checked={selected.has(row.id)} onChange={() => toggle(row.id)} aria-label={`Select ${row.description_clean}`}/></td>
              <td><div className="flag-stack">
                {row.duplicate_status === "duplicate" && <>
                  <Badge tone="danger">duplicate</Badge>
                  <label className="inline-check" title="Exact duplicates are excluded unless you explicitly include them">
                    <input
                      type="checkbox"
                      checked={row.review_status === "approved"}
                      disabled={row.review_status === "skipped"}
                      onChange={(event) => change(row, { review_status: event.target.checked ? "approved" : "pending" })}
                    />
                    Import anyway
                  </label>
                </>}
                {row.duplicate_status === "possible_duplicate" && <Badge tone="warn">possible duplicate</Badge>}
                {!row.category_id && <Badge tone="warn">uncategorized</Badge>}
                {row.rule_applied && <Badge tone="accent">rule</Badge>}
                {row.recurring_candidate && <Badge tone="good">recurring?</Badge>}
                {row.category_id && row.review_status === "edited" && <button className="button compact-button" onClick={() => createRule(row)}>Rule from edit</button>}
              </div></td>
              <td className="nowrap">{shortDate(row.transaction_date)}</td>
              <td><input className="input" value={row.description_clean} onChange={(event) => setRows((current) => current.map((candidate) => candidate.id === row.id ? { ...candidate, description_clean: event.target.value } : candidate))} onBlur={(event) => change(row, { description_clean: event.target.value })}/>{row.cardholder_name && <small className="muted">{row.cardholder_name}</small>}</td>
              <td className={`amount ${row.direction}`}>{row.direction === "inflow" ? "+" : "−"}{money(row.amount)}</td>
              <td>
                <select className="select" value={row.category_id || ""} onChange={(event) => {
                  if (event.target.value === ADD_CATEGORY_VALUE) {
                    openTaxonomyModal({ kind: "category", rowId: row.id });
                    return;
                  }
                  const categoryId = event.target.value || null;
                  const selectedCategory = categories.find((candidate) => candidate.id === categoryId);
                  const transactionType = impliedTransactionType(selectedCategory);
                  change(row, {
                    category_id: categoryId,
                    subcategory_id: soleActiveSubcategoryId(selectedCategory),
                    ...(transactionType ? { transaction_type: transactionType } : {}),
                  });
                }}>
                  <option value="">Uncategorized</option>
                  {categories.filter((candidate) => candidate.is_active).map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}
                  <option value={ADD_CATEGORY_VALUE}>Add new category…</option>
                </select>
                <select className="select" value={row.subcategory_id || ""} disabled={!category} onChange={(event) => {
                  if (event.target.value === ADD_SUBCATEGORY_VALUE && category) {
                    openTaxonomyModal({ kind: "subcategory", rowId: row.id, categoryId: category.id });
                    return;
                  }
                  change(row, { subcategory_id: event.target.value || null });
                }}>
                  <option value="">No subcategory</option>
                  {category?.subcategories.filter((subcategory) => subcategory.is_active).map((subcategory) => <option key={subcategory.id} value={subcategory.id}>{subcategory.name}</option>)}
                  {category && <option value={ADD_SUBCATEGORY_VALUE}>Add new subcategory…</option>}
                </select>
              </td>
              <td><select className="select" value={row.transaction_type} onChange={(event) => change(row, { transaction_type: event.target.value, is_excluded_from_spending: ["transfer", "credit_card_payment", "adjustment"].includes(event.target.value) })}>{types.map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}</select>{row.source_transaction_type && <small className="muted">Source: {row.source_transaction_type}</small>}</td>
              <td><select className="select" value={row.account_instrument_id || ""} onChange={(event) => change(row, { account_instrument_id: event.target.value || null })}><option value="">Parent account</option>{instruments.map((instrument) => <option key={instrument.id} value={instrument.id}>{instrument.display_name}</option>)}</select>{row.card_last_four && <small className="muted">Source •••• {row.card_last_four}</small>}</td>
              <td><input type="checkbox" checked={row.is_excluded_from_spending} onChange={(event) => change(row, { is_excluded_from_spending: event.target.checked })}/></td>
              <td><input type="checkbox" checked={row.is_recurring} onChange={(event) => change(row, { is_recurring: event.target.checked })}/></td>
              <td className="skip-cell"><input type="checkbox" checked={row.review_status === "skipped"} onChange={(event) => change(row, { review_status: event.target.checked ? "skipped" : "pending" })} aria-label={`Skip ${row.description_clean}`}/></td>
              <td><button className="icon-button danger" onClick={() => deleteDrafts([row.id])} disabled={deleting} aria-label={`Delete ${row.description_clean}`}><Trash2 size={16}/></button></td>
            </tr>;
          })}</tbody>
        </table>
      </div>}
    </div>
    {taxonomyModal && <div className="modal-backdrop">
      <div className="modal" style={{ width: "min(440px, 100%)" }} role="dialog" aria-modal="true" aria-labelledby="taxonomy-modal-title">
        <div className="modal-header">
          <h2 id="taxonomy-modal-title">Add new {taxonomyModal.kind}</h2>
          <button className="icon-button" type="button" onClick={closeTaxonomyModal} disabled={taxonomySaving} aria-label="Close category form"><X/></button>
        </div>
        {taxonomyError && <div className="notice notice-error">{taxonomyError}</div>}
        <form onSubmit={createTaxonomyItem}>
          {taxonomyModal.kind === "subcategory" && <div className="field" style={{ marginBottom: 14 }}>
            <label>Parent category</label>
            <input className="input" value={modalCategory?.name || ""} readOnly/>
          </div>}
          <div className="field">
            <label>Name</label>
            <input className="input" name="name" required maxLength={120} autoFocus/>
          </div>
          <div className="field" style={{ marginTop: 14 }}>
            <label>Description (optional)</label>
            <textarea className="textarea" name="description"/>
          </div>
          <div className="form-actions">
            <button type="button" className="button" onClick={closeTaxonomyModal} disabled={taxonomySaving}>Cancel</button>
            <button className="button button-primary" disabled={taxonomySaving}>{taxonomySaving ? "Saving…" : "Save"}</button>
          </div>
        </form>
      </div>
    </div>}
    {ruleDefaults && <RuleForm
      categories={categories}
      mode="create"
      initialValues={ruleDefaults}
      onClose={() => setRuleDefaults(null)}
      onSuccess={(rule) => { void applyCreatedRule(rule); }}
    />}
  </>;
}
