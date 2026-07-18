"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Badge, PageHeader } from "@/components/Page";
import { api } from "@/lib/api";
import type { ImportRecord, Institution } from "@/lib/types";

const roles = [
  { key: "date_column", label: "Transaction date" },
  { key: "post_date_column", label: "Posted date" },
  { key: "description_column", label: "Description" },
  { key: "merchant_column", label: "Merchant" },
  { key: "amount_column", label: "Amount" },
  { key: "debit_column", label: "Debit" },
  { key: "credit_column", label: "Credit" },
  { key: "category_column", label: "Provider category" },
  { key: "provider_type_column", label: "Provider transaction type" },
  { key: "transaction_id_column", label: "Transaction ID" },
  { key: "notes_column", label: "Notes" },
  { key: "card_number_column", label: "Card number" },
  { key: "card_last_four_column", label: "Card last four" },
  { key: "cardholder_name_column", label: "Cardholder / authorized user" },
  { key: "account_suffix_column", label: "Account suffix / source identifier" },
] as const;

type RoleKey = (typeof roles)[number]["key"];

function proposedValue(proposed: Record<string, unknown>, key: string): string {
  return typeof proposed[key] === "string" ? proposed[key] : "";
}

export default function MappingPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [item, setItem] = useState<ImportRecord | null>(null);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [institutionId, setInstitutionId] = useState("");
  const [assignments, setAssignments] = useState<Record<string, RoleKey | "">>({});
  const [amountBehavior, setAmountBehavior] = useState("signed_amount");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [force, setForce] = useState(false);

  useEffect(() => {
    Promise.all([
      api<ImportRecord>(`/imports/${id}`),
      api<Institution[]>("/institutions"),
    ])
      .then(([record, institutionRows]) => {
        setItem(record);
        setInstitutions(institutionRows);
        setInstitutionId(record.institution_id || "");

        const proposed = record.proposed_mapping || {};
        const initialAssignments: Record<string, RoleKey | ""> = Object.fromEntries(
          (record.headers || []).map((header) => [header, ""]),
        );
        for (const role of roles) {
          const header = proposedValue(proposed, role.key);
          if (header && header in initialAssignments && !initialAssignments[header]) {
            initialAssignments[header] = role.key;
          }
        }
        setAssignments(initialAssignments);
        setAmountBehavior(proposedValue(proposed, "amount_behavior") || "signed_amount");
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Could not load import"));
  }, [id]);

  const proposed = item?.proposed_mapping || {};
  const confidence = useMemo(() => {
    const value = proposed.confidence;
    return value && typeof value === "object" ? value as Record<string, number> : {};
  }, [proposed]);

  async function addInstitution() {
    const name = window.prompt("Institution name");
    if (!name?.trim()) return;
    try {
      const created = await api<Institution>("/institutions", {
        method: "POST",
        body: JSON.stringify({ display_name: name }),
      });
      setInstitutions((current) => [
        ...current.filter((row) => row.id !== created.id),
        created,
      ].sort((left, right) => left.display_name.localeCompare(right.display_name)));
      setInstitutionId(created.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not add institution");
    }
  }

  function assignRole(header: string, role: RoleKey | "") {
    setAssignments((current) => {
      const next = { ...current };
      if (role) {
        for (const candidate of Object.keys(next)) {
          if (next[candidate] === role) next[candidate] = "";
        }
      }
      next[header] = role;
      return next;
    });
  }

  function mappingError(): string | null {
    const assignedRoles = new Set(Object.values(assignments).filter(Boolean));
    if (!assignedRoles.has("date_column") && !assignedRoles.has("post_date_column")) {
      return "Assign a transaction date or posted date column.";
    }
    if (!assignedRoles.has("description_column")) {
      return "Assign a description column.";
    }
    if (amountBehavior === "debit_credit_columns") {
      if (!assignedRoles.has("debit_column") && !assignedRoles.has("credit_column")) {
        return "Assign at least one debit or credit column.";
      }
    } else if (!assignedRoles.has("amount_column")) {
      return "Assign an amount column.";
    }
    return null;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = mappingError();
    if (validationError) {
      setError(validationError);
      return;
    }

    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const payload: Record<string, unknown> = {
      institution_id: institutionId,
      account_type: form.get("account_type"),
      mapping_name: form.get("mapping_name"),
      amount_behavior: amountBehavior,
    };
    for (const role of roles) payload[role.key] = null;
    for (const [header, role] of Object.entries(assignments)) {
      if (role) payload[role] = header;
    }

    try {
      const mapping = await api<{ id: string }>(`/imports/${id}/mapping`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await api(`/imports/${id}/normalize?mapping_id=${mapping.id}&force_duplicate_file=${force}`, {
        method: "POST",
      });
      router.push(`/imports/${id}/review`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not normalize file");
      setBusy(false);
    }
  }

  function statusFor(header: string) {
    const role = assignments[header];
    if (!role) return <Badge>Ignored</Badge>;
    const proposedRole = roles.find((candidate) => proposedValue(proposed, candidate.key) === header)?.key;
    if (proposedRole !== role) return <Badge tone="good">Manual</Badge>;
    if (proposed.mapping_source === "saved") return <Badge tone="good">Saved</Badge>;
    return (confidence[role] || 0) >= 0.95
      ? <Badge tone="accent">Auto</Badge>
      : <Badge tone="warn">Needs review</Badge>;
  }

  if (!item) {
    return <>
      <PageHeader title="Inspecting CSV…" />
      {error && <div className="notice notice-error">{error}</div>}
    </>;
  }

  const sample = item.sample_rows?.[0] || {};
  return <>
    <div className="steps"><div className="step done"/><div className="step active"/><div className="step"/></div>
    <PageHeader
      eyebrow="Step 2 of 3"
      title="Confirm what each CSV column means"
      description="Every source column is shown once. Confirm the suggestions, assign a different app field, or leave a column ignored."
    />
    {item.is_duplicate_file && <div className="notice notice-warn">
      <strong>This exact file was uploaded before.</strong> Importing is blocked by default.{" "}
      <label><input type="checkbox" checked={force} onChange={(event) => setForce(event.target.checked)}/> Continue anyway</label>
    </div>}
    {error && <div className="notice notice-error">{error}</div>}

    <form onSubmit={submit}>
      <div className="card card-pad"><div className="form-grid">
        <div className="field full"><label>Financial institution</label><div className="institution-picker">
          <select className="select" value={institutionId} onChange={(event) => setInstitutionId(event.target.value)} required>
            <option value="">Choose an institution</option>
            {institutions.filter((row) => row.is_active).map((row) => <option key={row.id} value={row.id}>{row.display_name}</option>)}
          </select>
          <button type="button" className="button" onClick={addInstitution}>Add institution</button>
        </div></div>
        <div className="field"><label>Account type</label><select className="select" name="account_type" defaultValue={item.account_type || "other"}>
          <option value="checking">Checking</option><option value="savings">Savings</option><option value="credit_card">Credit card</option><option value="cash">Cash</option><option value="other">Other</option>
        </select></div>
        <div className="field"><label>Mapping name</label><input className="input" name="mapping_name" defaultValue={`${item.institution_name || "Custom"} CSV`} required/></div>
        <div className="field"><label>Amount behavior</label><select className="select" value={amountBehavior} onChange={(event) => setAmountBehavior(event.target.value)}>
          <option value="signed_amount">Signed amount (positive inflow)</option><option value="charges_positive">Charges are positive</option><option value="charges_negative">Charges are negative</option><option value="debit_credit_columns">Separate debit / credit columns</option><option value="credits_positive">Credits are positive</option><option value="credits_negative">Credits are negative</option>
        </select></div>
      </div></div>

      <div className="section-title"><div>
        <h2>CSV columns</h2>
        <p>{item.headers?.length} headers · provider labels are preserved and translated during normalization</p>
      </div></div>
      <div className="card">
        <div className="mapping-row header"><span>CSV column</span><span>Sample value</span><span>Import as</span><span>Status</span></div>
        {item.headers?.map((header) => <div className="mapping-row" key={header}>
          <strong>{header}</strong>
          <span className="muted">{sample[header] || "—"}</span>
          <select className="select" value={assignments[header] || ""} onChange={(event) => assignRole(header, event.target.value as RoleKey | "")}>
            <option value="">Ignore this column</option>
            {roles.map((role) => <option key={role.key} value={role.key}>{role.label}</option>)}
          </select>
          <span>{statusFor(header)}</span>
        </div>)}
      </div>
      <div className="notice notice-warn mapping-help">
        <strong>Provider category and provider transaction type are source labels.</strong> Institution mappings translate them into your category, subcategory, and transaction type before rules run.
      </div>
      <div className="form-actions">
        <button type="button" className="button" onClick={() => router.push("/imports")}>Save for later</button>
        <button className="button button-primary" disabled={busy || (item.is_duplicate_file && !force)}>{busy ? "Creating drafts…" : "Save mapping & review"}</button>
      </div>
    </form>
  </>;
}
