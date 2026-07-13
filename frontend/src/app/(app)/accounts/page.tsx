"use client";

import { FormEvent, useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { Badge, EmptyState, PageHeader } from "@/components/Page";
import { api } from "@/lib/api";
import type { Account, Institution, Instrument } from "@/lib/types";

type Modal = "account" | "edit-account" | "instrument" | null;

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [instruments, setInstruments] = useState<Record<string, Instrument[]>>({});
  const [modal, setModal] = useState<Modal>(null);
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);
  const [institutionId, setInstitutionId] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const [accountRows, institutionRows] = await Promise.all([
      api<Account[]>("/accounts"),
      api<Institution[]>("/institutions"),
    ]);
    setAccounts(accountRows);
    setInstitutions(institutionRows);
    const pairs = await Promise.all(
      accountRows.map(async (row) => [row.id, await api<Instrument[]>(`/accounts/${row.id}/instruments`)] as const),
    );
    setInstruments(Object.fromEntries(pairs));
  }

  useEffect(() => { load(); }, []);

  async function createInstitution() {
    const displayName = window.prompt("Institution name");
    if (!displayName?.trim()) return;
    try {
      const institution = await api<Institution>("/institutions", {
        method: "POST",
        body: JSON.stringify({ display_name: displayName }),
      });
      setInstitutions((current) =>
        [...current.filter((item) => item.id !== institution.id), institution]
          .sort((a, b) => a.display_name.localeCompare(b.display_name)),
      );
      setInstitutionId(institution.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not add institution");
    }
  }

  async function saveAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = {
      name: form.get("name"),
      institution_id: institutionId || null,
      account_type: form.get("type"),
      last_four: form.get("last_four") || null,
      currency: "USD",
      statement_cycle_day: form.get("cycle") ? Number(form.get("cycle")) : null,
      payment_due_day: form.get("due") ? Number(form.get("due")) : null,
    };
    try {
      if (modal === "edit-account" && selectedAccount) {
        await api(`/accounts/${selectedAccount.id}`, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        await api("/accounts", { method: "POST", body: JSON.stringify(payload) });
      }
      setModal(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save account");
    }
  }

  async function addInstrument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedAccount) return;
    const form = new FormData(event.currentTarget);
    try {
      await api(`/accounts/${selectedAccount.id}/instruments`, {
        method: "POST",
        body: JSON.stringify({
          instrument_type: form.get("type"),
          display_name: form.get("name"),
          cardholder_name: form.get("holder") || null,
          last_four: form.get("last_four") || null,
          source_identifier: form.get("last_four") ? `xxxx${form.get("last_four")}` : null,
        }),
      });
      setModal(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save card/profile");
    }
  }

  async function disable(id: string) {
    await api(`/accounts/${id}`, { method: "DELETE" });
    await load();
  }

  async function editInstrument(item: Instrument) {
    const displayName = window.prompt("Card/profile display name", item.display_name);
    if (!displayName) return;
    const cardholderName = window.prompt("Cardholder name", item.cardholder_name || "");
    await api(`/account-instruments/${item.id}`, {
      method: "PATCH",
      body: JSON.stringify({ display_name: displayName, cardholder_name: cardholderName || null }),
    });
    await load();
  }

  async function disableInstrument(item: Instrument) {
    await api(`/account-instruments/${item.id}`, { method: "DELETE" });
    await load();
  }

  function openNewAccount() {
    setSelectedAccount(null);
    setInstitutionId("");
    setError("");
    setModal("account");
  }

  function openEditAccount(account: Account) {
    setSelectedAccount(account);
    setInstitutionId(account.institution_id || "");
    setError("");
    setModal("edit-account");
  }

  const activeInstitutions = institutions.filter((item) => item.is_active);

  return <>
    <PageHeader
      eyebrow="Financial accounts"
      title="Accounts & cards"
      description="Keep statement accounts as parents. Add physical cards and authorized users beneath them for attribution."
      actions={<button className="button button-primary" onClick={openNewAccount}><Plus size={16}/>Add account</button>}
    />
    {!accounts.length ? <div className="card">
      <EmptyState
        title="Add your first account"
        body="Create a checking, savings, cash, or credit card account before importing transactions."
        action={<button className="button button-primary" onClick={openNewAccount}>Add account</button>}
      />
    </div> : <div className="grid grid-3">{accounts.map((item) => <div className="card account-card" key={item.id}>
      <div className="account-head"><div>
        <h3>{item.name}</h3>
        <span className="account-meta">{item.institution?.display_name || "No institution"}{item.last_four && ` · •••• ${item.last_four}`}</span>
      </div><Badge tone={item.is_active ? "good" : "neutral"}>{item.account_type.replaceAll("_", " ")}</Badge></div>
      <div className="instrument-list">
        {(instruments[item.id] || []).map((instrument) => <div className="instrument-row" key={instrument.id}>
          <span>{instrument.display_name}{instrument.last_four && ` · ${instrument.last_four}`}</span>
          <span className="page-actions">{!instrument.is_active && <Badge>disabled</Badge>}
            <button className="icon-button" onClick={() => editInstrument(instrument)}>Edit</button>
            {instrument.is_active && <button className="icon-button danger" onClick={() => disableInstrument(instrument)}>Disable</button>}
          </span>
        </div>)}
        <button className="button" onClick={() => { setSelectedAccount(item); setModal("instrument"); }}><Plus size={14}/>Add card/profile</button>
        <button className="button" onClick={() => openEditAccount(item)}>Edit account</button>
        {item.is_active && <button className="button button-danger" onClick={() => disable(item.id)}>Disable account</button>}
      </div>
    </div>)}</div>}

    {modal && <div className="modal-backdrop"><div className="modal">
      <div className="modal-header"><h2>{modal === "instrument" ? "Add card or profile" : modal === "edit-account" ? "Edit financial account" : "Add financial account"}</h2><button className="icon-button" onClick={() => setModal(null)}><X/></button></div>
      {error && <div className="notice notice-error">{error}</div>}
      {modal !== "instrument" ? <form onSubmit={saveAccount}>
        <div className="form-grid">
          <div className="field full"><label>Account name</label><input className="input" name="name" placeholder="Chase Sapphire Preferred" defaultValue={selectedAccount?.name || ""} required/></div>
          <div className="field full"><label>Financial institution</label><div className="institution-picker">
            <select className="select" name="institution_id" value={institutionId} onChange={(event) => setInstitutionId(event.target.value)}>
              <option value="">No institution / manual account</option>
              {activeInstitutions.map((institution) => <option key={institution.id} value={institution.id}>{institution.display_name}</option>)}
            </select>
            <button className="button" type="button" onClick={createInstitution}><Plus size={14}/>Add institution</button>
          </div></div>
          <div className="field"><label>Account type</label><select className="select" name="type" defaultValue={selectedAccount?.account_type || "checking"}><option value="checking">Checking</option><option value="savings">Savings</option><option value="credit_card">Credit card</option><option value="cash">Cash</option><option value="other">Other</option></select></div>
          <div className="field"><label>Last four (optional)</label><input className="input" name="last_four" pattern="[0-9]{4}" maxLength={4} defaultValue={selectedAccount?.last_four || ""}/></div>
          <div className="field"><label>Statement cycle day</label><input className="input" type="number" name="cycle" min={1} max={31} defaultValue={selectedAccount?.statement_cycle_day || ""}/></div>
          <div className="field"><label>Payment due day</label><input className="input" type="number" name="due" min={1} max={31} defaultValue={selectedAccount?.payment_due_day || ""}/></div>
        </div>
        <div className="form-actions"><button type="button" className="button" onClick={() => setModal(null)}>Cancel</button><button className="button button-primary">Save account</button></div>
      </form> : <form onSubmit={addInstrument}>
        <div className="form-grid">
          <div className="field full"><label>Display name</label><input className="input" name="name" placeholder="Spouse card ending 5678" required/></div>
          <div className="field"><label>Type</label><select className="select" name="type"><option value="credit_card">Credit card</option><option value="authorized_user_card">Authorized user card</option><option value="debit_card">Debit card</option><option value="other">Other</option></select></div>
          <div className="field"><label>Cardholder</label><input className="input" name="holder"/></div>
          <div className="field"><label>Last four</label><input className="input" name="last_four" pattern="[0-9]{4}" maxLength={4}/></div>
        </div>
        <div className="form-actions"><button type="button" className="button" onClick={() => setModal(null)}>Cancel</button><button className="button button-primary">Save profile</button></div>
      </form>}
    </div></div>}
  </>;
}
