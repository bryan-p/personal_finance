"use client";

import { Trash2 } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Badge, EmptyState, PageHeader } from "@/components/Page";
import { api, money, shortDate } from "@/lib/api";
import type { Category, DraftTransaction, ImportRecord, Instrument } from "@/lib/types";

const types = ["expense", "income", "transfer", "credit_card_payment", "refund", "fee", "adjustment", "other"];

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [rows, setRows] = useState<DraftTransaction[]>([]);
  const [item, setItem] = useState<ImportRecord | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [filter, setFilter] = useState("");

  async function load() {
    try {
      const [drafts, info, cats] = await Promise.all([
        api<DraftTransaction[]>(`/imports/${id}/review${filter ? `?instrument_id=${filter}` : ""}`),
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

  useEffect(() => { load(); }, [id, filter]);

  async function change(row: DraftTransaction, changes: Record<string, unknown>) {
    setRows((current) => current.map((candidate) => candidate.id === row.id
      ? { ...candidate, ...changes, review_status: "edited" } as DraftTransaction
      : candidate));
    try {
      await api(`/imports/${id}/draft-transactions/${row.id}`, {
        method: "PATCH",
        body: JSON.stringify(changes),
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save edit");
      await load();
    }
  }

  async function createRule(row: DraftTransaction) {
    const token = row.description_clean.split(/\s+/).find((part) => part.length >= 4) || row.description_clean;
    if (!window.confirm(`Create a rule that categorizes descriptions containing “${token}”?`)) return;
    try {
      await api("/rules", {
        method: "POST",
        body: JSON.stringify({
          name: `Categorize ${token}`,
          priority: 100,
          is_active: true,
          match_field: "description",
          match_operator: "contains",
          match_value: token,
          category_id: row.category_id || null,
          subcategory_id: row.subcategory_id || null,
          transaction_type: null,
          is_excluded_from_spending: null,
          mark_as_recurring: null,
          merchant_name_override: row.merchant_name || null,
          note: null,
        }),
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create rule");
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
    setSelected(selected.size === rows.length ? new Set() : new Set(rows.map((row) => row.id)));
  }

  const counts = useMemo(() => ({
    duplicate: rows.filter((row) => row.duplicate_status === "duplicate").length,
    uncategorized: rows.filter((row) => !row.category_id).length,
    rules: rows.filter((row) => row.rule_applied).length,
  }), [rows]);
  const allSelected = rows.length > 0 && selected.size === rows.length;

  return <>
    <div className="steps"><div className="step done"/><div className="step done"/><div className="step active"/></div>
    <PageHeader
      eyebrow="Step 3 of 3"
      title="Review draft transactions"
      description={`${item?.original_filename || "CSV"} · ${rows.length} rows. Edits save immediately, so you can safely return later.`}
      actions={<>
        <button className="button" onClick={() => router.push("/imports")}>Resume later</button>
        <button className="button button-primary" onClick={confirm} disabled={confirming || deleting}>{confirming ? "Importing…" : "Confirm import"}</button>
      </>}
    />
    {error && <div className="notice notice-error">{error}</div>}
    <div className="toolbar">
      <Badge tone={counts.duplicate ? "danger" : "good"}>{counts.duplicate} duplicates</Badge>
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
      {!rows.length ? <EmptyState title="No draft rows" body="Normalize the import mapping first, or clear the active card/profile filter."/> : <div className="table-scroll">
        <table className="data-table">
          <thead><tr>
            <th className="selection-cell"><input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="Select all displayed draft transactions"/></th>
            <th>Flags</th><th>Date</th><th>Description</th><th>Amount</th><th>Category</th><th>Type</th><th>Card/profile</th><th>Excluded</th><th>Recurring</th><th>Review</th><th>Actions</th>
          </tr></thead>
          <tbody>{rows.map((row) => {
            const category = categories.find((candidate) => candidate.id === row.category_id);
            return <tr key={row.id} className={row.is_excluded_from_spending ? "excluded-row" : ""}>
              <td className="selection-cell"><input type="checkbox" checked={selected.has(row.id)} onChange={() => toggle(row.id)} aria-label={`Select ${row.description_clean}`}/></td>
              <td><div className="flag-stack">
                {row.duplicate_status !== "new" && <Badge tone="danger">duplicate</Badge>}
                {!row.category_id && <Badge tone="warn">uncategorized</Badge>}
                {row.rule_applied && <Badge tone="accent">rule</Badge>}
                {row.recurring_candidate && <Badge tone="good">recurring?</Badge>}
                {row.category_id && row.review_status === "edited" && <button className="button compact-button" onClick={() => createRule(row)}>Rule from edit</button>}
              </div></td>
              <td className="nowrap">{shortDate(row.transaction_date)}</td>
              <td><input className="input" value={row.description_clean} onChange={(event) => setRows((current) => current.map((candidate) => candidate.id === row.id ? { ...candidate, description_clean: event.target.value } : candidate))} onBlur={(event) => change(row, { description_clean: event.target.value })}/>{row.cardholder_name && <small className="muted">{row.cardholder_name}</small>}</td>
              <td className={`amount ${row.direction}`}>{row.direction === "inflow" ? "+" : "−"}{money(row.amount)}</td>
              <td>
                <select className="select" value={row.category_id || ""} onChange={(event) => change(row, { category_id: event.target.value || null, subcategory_id: null })}><option value="">Uncategorized</option>{categories.filter((candidate) => candidate.is_active).map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}</select>
                <select className="select" value={row.subcategory_id || ""} onChange={(event) => change(row, { subcategory_id: event.target.value || null })}><option value="">No subcategory</option>{category?.subcategories.filter((subcategory) => subcategory.is_active).map((subcategory) => <option key={subcategory.id} value={subcategory.id}>{subcategory.name}</option>)}</select>
              </td>
              <td><select className="select" value={row.transaction_type} onChange={(event) => change(row, { transaction_type: event.target.value, is_excluded_from_spending: ["transfer", "credit_card_payment", "adjustment"].includes(event.target.value) })}>{types.map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}</select></td>
              <td><select className="select" value={row.account_instrument_id || ""} onChange={(event) => change(row, { account_instrument_id: event.target.value || null })}><option value="">Parent account</option>{instruments.map((instrument) => <option key={instrument.id} value={instrument.id}>{instrument.display_name}</option>)}</select>{row.card_last_four && <small className="muted">Source •••• {row.card_last_four}</small>}</td>
              <td><input type="checkbox" checked={row.is_excluded_from_spending} onChange={(event) => change(row, { is_excluded_from_spending: event.target.checked })}/></td>
              <td><input type="checkbox" checked={row.is_recurring} onChange={(event) => change(row, { is_recurring: event.target.checked })}/></td>
              <td><select className="select" value={row.review_status} onChange={(event) => change(row, { review_status: event.target.value })}><option value="pending">Pending</option><option value="approved">Approved</option><option value="skipped">Skip</option></select></td>
              <td><button className="icon-button danger" onClick={() => deleteDrafts([row.id])} disabled={deleting} aria-label={`Delete ${row.description_clean}`}><Trash2 size={16}/></button></td>
            </tr>;
          })}</tbody>
        </table>
      </div>}
    </div>
  </>;
}
