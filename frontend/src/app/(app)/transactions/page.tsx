"use client";

import { Download, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge, EmptyState, PageHeader } from "@/components/Page";
import { API_BASE, api, money, shortDate } from "@/lib/api";
import type { Account, Category, Instrument, Transaction } from "@/lib/types";

const transactionTypes = ["expense", "income", "transfer", "credit_card_payment", "refund", "fee", "adjustment", "other"];

interface Filters {
  search: string;
  account_id: string;
  account_instrument_id: string;
  category_id: string;
  transaction_type: string;
  start_date: string;
  end_date: string;
}

const initialFilters: Filters = {
  search: "",
  account_id: "",
  account_instrument_id: "",
  category_id: "",
  transaction_type: "",
  start_date: "",
  end_date: "",
};

export default function TransactionsPage() {
  const [rows, setRows] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  const query = useMemo(() => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([name, value]) => value && params.set(name, value));
    return params.toString();
  }, [filters]);

  async function loadTransactions() {
    try {
      const separator = query ? "&" : "";
      setRows(await api<Transaction[]>(`/transactions?${query}${separator}limit=1000`));
      setSelected(new Set());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load transactions");
    }
  }

  useEffect(() => {
    Promise.all([api<Account[]>("/accounts"), api<Category[]>("/categories")])
      .then(([accountRows, categoryRows]) => {
        setAccounts(accountRows);
        setCategories(categoryRows);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Could not load filters"));
  }, []);

  useEffect(() => { loadTransactions(); }, [query]);

  useEffect(() => {
    if (!filters.account_id) {
      setInstruments([]);
      return;
    }
    api<Instrument[]>(`/accounts/${filters.account_id}/instruments`)
      .then(setInstruments)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Could not load cards or profiles"));
  }, [filters.account_id]);

  async function change(row: Transaction, changes: Record<string, unknown>) {
    setRows((current) => current.map((candidate) => candidate.id === row.id
      ? { ...candidate, ...changes } as Transaction
      : candidate));
    try {
      await api(`/transactions/${row.id}`, {
        method: "PATCH",
        body: JSON.stringify(changes),
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save transaction");
      await loadTransactions();
    }
  }

  async function deleteTransactions(ids: string[]) {
    const label = ids.length === 1 ? "this confirmed transaction" : `${ids.length} confirmed transactions`;
    if (!window.confirm(`Permanently delete ${label}? Dashboard totals and exports will update immediately.`)) return;
    setDeleting(true);
    try {
      if (ids.length === 1) {
        await api(`/transactions/${ids[0]}`, { method: "DELETE" });
      } else {
        await api("/transactions/bulk-delete", {
          method: "POST",
          body: JSON.stringify({ ids }),
        });
      }
      const deleted = new Set(ids);
      setRows((current) => current.filter((row) => !deleted.has(row.id)));
      setSelected((current) => new Set([...current].filter((rowId) => !deleted.has(rowId))));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete transactions");
      await loadTransactions();
    } finally {
      setDeleting(false);
    }
  }

  function setFilter(name: keyof Filters, value: string) {
    setFilters((current) => name === "account_id"
      ? { ...current, account_id: value, account_instrument_id: "" }
      : { ...current, [name]: value });
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

  const allSelected = rows.length > 0 && selected.size === rows.length;

  return <>
    <PageHeader
      eyebrow="Ledger"
      title="Transactions"
      description="Search, filter, correct, delete, and export normalized confirmed transactions."
      actions={<a className="button" href={`${API_BASE}/transactions/export?${query}`}><Download size={16}/>Export CSV</a>}
    />
    {error && <div className="notice notice-error">{error}</div>}
    {selected.size > 0 && <div className="selection-bar">
      <strong>{selected.size} displayed transaction{selected.size === 1 ? "" : "s"} selected</strong>
      <button className="button button-danger" onClick={() => deleteTransactions([...selected])} disabled={deleting}><Trash2 size={15}/>{deleting ? "Deleting…" : "Delete selected"}</button>
    </div>}
    <div className="toolbar">
      <div className="field grow"><label>Search</label><div className="search-field"><Search size={16}/><input className="input" value={filters.search} onChange={(event) => setFilter("search", event.target.value)} placeholder="Merchant or description"/></div></div>
      <div className="field"><label>From</label><input className="input" type="date" value={filters.start_date} onChange={(event) => setFilter("start_date", event.target.value)}/></div>
      <div className="field"><label>To</label><input className="input" type="date" value={filters.end_date} onChange={(event) => setFilter("end_date", event.target.value)}/></div>
      <div className="field"><label>Account</label><select className="select" value={filters.account_id} onChange={(event) => setFilter("account_id", event.target.value)}><option value="">All</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select></div>
      <div className="field"><label>Card/profile</label><select className="select" value={filters.account_instrument_id} onChange={(event) => setFilter("account_instrument_id", event.target.value)} disabled={!filters.account_id}><option value="">All</option>{instruments.map((instrument) => <option key={instrument.id} value={instrument.id}>{instrument.display_name}</option>)}</select></div>
      <div className="field"><label>Category</label><select className="select" value={filters.category_id} onChange={(event) => setFilter("category_id", event.target.value)}><option value="">All</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></div>
      <div className="field"><label>Type</label><select className="select" value={filters.transaction_type} onChange={(event) => setFilter("transaction_type", event.target.value)}><option value="">All</option>{transactionTypes.map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}</select></div>
    </div>
    <div className="card table-card">
      {!rows.length ? <EmptyState title="No matching transactions" body="Confirmed imports appear here. Try clearing filters or import a CSV."/> : <div className="table-scroll">
        <table className="data-table">
          <thead><tr>
            <th className="selection-cell"><input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="Select all displayed confirmed transactions"/></th>
            <th>Date</th><th>Description</th><th>Account</th><th>Category</th><th>Type</th><th>Amount</th><th>Status</th><th>Actions</th>
          </tr></thead>
          <tbody>{rows.map((row) => {
            const account = accounts.find((candidate) => candidate.id === row.account_id);
            return <tr key={row.id} className={row.is_excluded_from_spending ? "excluded-row" : ""}>
              <td className="selection-cell"><input type="checkbox" checked={selected.has(row.id)} onChange={() => toggle(row.id)} aria-label={`Select ${row.merchant_name || row.description_clean}`}/></td>
              <td>{shortDate(row.transaction_date)}</td>
              <td><strong>{row.merchant_name || row.description_clean}</strong>{row.merchant_name && <div className="muted">{row.description_clean}</div>}</td>
              <td>{account?.name || "—"}{row.card_last_four && <div className="muted">Card {row.card_last_four}</div>}</td>
              <td><select className="select" value={row.category_id || ""} onChange={(event) => change(row, { category_id: event.target.value || null, subcategory_id: null })}><option value="">Uncategorized</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></td>
              <td><select className="select" value={row.transaction_type} onChange={(event) => change(row, { transaction_type: event.target.value })}>{transactionTypes.map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}</select></td>
              <td className={`amount ${row.direction}`}>{row.direction === "inflow" ? "+" : "−"}{money(row.amount)}</td>
              <td><div className="flag-stack">{row.is_excluded_from_spending && <Badge>excluded</Badge>}{row.is_recurring && <Badge tone="good">recurring</Badge>}{!row.category_id && <Badge tone="warn">review</Badge>}</div></td>
              <td><button className="icon-button danger" onClick={() => deleteTransactions([row.id])} disabled={deleting} aria-label={`Delete ${row.merchant_name || row.description_clean}`}><Trash2 size={16}/></button></td>
            </tr>;
          })}</tbody>
        </table>
      </div>}
    </div>
  </>;
}
