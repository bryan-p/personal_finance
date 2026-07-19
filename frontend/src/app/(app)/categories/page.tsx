"use client";

import { FormEvent, useEffect, useState } from "react";
import { Plus, Trash2, X } from "lucide-react";
import { Badge, PageHeader } from "@/components/Page";
import { api } from "@/lib/api";
import { soleActiveSubcategoryId } from "@/lib/categories";
import type { Category, Institution } from "@/lib/types";

interface ProviderCategoryMap {
  id: string;
  institution_id: string;
  institution: Institution;
  source_category: string;
  category_id: string;
  subcategory_id?: string;
}

interface ProviderTypeMap {
  id: string;
  institution_id: string;
  institution: Institution;
  source_transaction_type: string;
  transaction_type: string;
}

type Modal = "category" | "subcategory" | "provider category" | "provider type" | null;

const transactionTypes = [
  "expense", "income", "transfer", "credit_card_payment", "refund", "fee", "adjustment", "other",
];

export default function CategoriesPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [categoryMappings, setCategoryMappings] = useState<ProviderCategoryMap[]>([]);
  const [typeMappings, setTypeMappings] = useState<ProviderTypeMap[]>([]);
  const [modal, setModal] = useState<Modal>(null);
  const [parent, setParent] = useState("");
  const [providerSubcategory, setProviderSubcategory] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const [categoryRows, institutionRows, categoryMapRows, typeMapRows] = await Promise.all([
      api<Category[]>("/categories"),
      api<Institution[]>("/institutions"),
      api<ProviderCategoryMap[]>("/provider-category-mappings"),
      api<ProviderTypeMap[]>("/provider-transaction-type-mappings"),
    ]);
    setCategories(categoryRows);
    setInstitutions(institutionRows);
    setCategoryMappings(categoryMapRows);
    setTypeMappings(typeMapRows);
  }

  useEffect(() => { load().catch((reason) => setError(reason.message)); }, []);

  function openModal(next: Exclude<Modal, null>, categoryId = "") {
    setError("");
    setParent(categoryId);
    setProviderSubcategory("");
    setModal(next);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      if (modal === "category") {
        await api("/categories", {
          method: "POST",
          body: JSON.stringify({ name: form.get("name"), description: form.get("description") || null }),
        });
      } else if (modal === "subcategory") {
        await api("/subcategories", {
          method: "POST",
          body: JSON.stringify({ category_id: parent, name: form.get("name"), description: form.get("description") || null }),
        });
      } else if (modal === "provider category") {
        await api("/provider-category-mappings", {
          method: "POST",
          body: JSON.stringify({
            institution_id: form.get("institution_id"),
            source_category: form.get("source"),
            category_id: form.get("category"),
            subcategory_id: form.get("subcategory") || null,
          }),
        });
      } else if (modal === "provider type") {
        await api("/provider-transaction-type-mappings", {
          method: "POST",
          body: JSON.stringify({
            institution_id: form.get("institution_id"),
            source_transaction_type: form.get("source"),
            transaction_type: form.get("transaction_type"),
          }),
        });
      }
      setModal(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save");
    }
  }

  async function disable(category: Category) {
    await api(`/categories/${category.id}`, { method: "DELETE" });
    await load();
  }

  async function deleteMapping(kind: "category" | "type", id: string) {
    const path = kind === "category"
      ? `/provider-category-mappings/${id}`
      : `/provider-transaction-type-mappings/${id}`;
    try {
      await api(path, { method: "DELETE" });
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete mapping");
    }
  }

  return <>
    <PageHeader
      eyebrow="Taxonomy"
      title="Categories"
      description="Your categories are the source of truth; provider category and type labels are preserved separately."
      actions={<button className="button button-primary" onClick={() => openModal("category")}><Plus size={16}/>New category</button>}
    />
    {error && <div className="notice notice-error">{error}</div>}

    <div className="grid grid-3">{categories.map((category) => <div className="card account-card" key={category.id}>
      <div className="account-head"><div><h3>{category.name}</h3><span className="account-meta">{category.subcategories.length} subcategories</span></div><Badge tone={category.is_active ? "good" : "neutral"}>{category.is_system ? "starter" : "custom"}</Badge></div>
      <div className="instrument-list">
        {category.subcategories.map((subcategory) => <div className="instrument-row" key={subcategory.id}>{subcategory.name}{!subcategory.is_active && <Badge>disabled</Badge>}</div>)}
        <button className="button" onClick={() => openModal("subcategory", category.id)}><Plus size={14}/>Add subcategory</button>
        {category.is_active && <button className="button button-danger" onClick={() => disable(category)}>Disable category</button>}
      </div>
    </div>)}</div>

    <div className="section-title"><div>
      <h2>Institution category mappings</h2>
      <p>Translate source category labels into your taxonomy before explicit rules override them.</p>
    </div><button className="button" onClick={() => openModal("provider category")}><Plus size={14}/>Add mapping</button></div>
    <div className="card table-card"><div className="table-scroll"><table className="data-table">
      <thead><tr><th>Institution</th><th>Source category</th><th>App category</th><th>Subcategory</th><th/></tr></thead>
      <tbody>{categoryMappings.length ? categoryMappings.map((mapping) => {
        const category = categories.find((candidate) => candidate.id === mapping.category_id);
        return <tr key={mapping.id}>
          <td>{mapping.institution.display_name}</td><td><Badge tone="accent">{mapping.source_category}</Badge></td>
          <td>{category?.name || "—"}</td><td>{category?.subcategories.find((subcategory) => subcategory.id === mapping.subcategory_id)?.name || "—"}</td>
          <td><button className="icon-button danger" onClick={() => deleteMapping("category", mapping.id)} aria-label={`Delete ${mapping.source_category} mapping`}><Trash2 size={15}/></button></td>
        </tr>;
      }) : <tr><td colSpan={5} className="muted">No institution category mappings yet.</td></tr>}</tbody>
    </table></div></div>

    <div className="section-title"><div>
      <h2>Provider transaction type mappings</h2>
      <p>Translate values such as Sale, Payment, or Return into Ledgerly transaction types before rules run.</p>
    </div><button className="button" onClick={() => openModal("provider type")}><Plus size={14}/>Add mapping</button></div>
    <div className="card table-card"><div className="table-scroll"><table className="data-table">
      <thead><tr><th>Institution</th><th>Provider type</th><th>Ledgerly type</th><th>Spending treatment</th><th/></tr></thead>
      <tbody>{typeMappings.length ? typeMappings.map((mapping) => <tr key={mapping.id}>
        <td>{mapping.institution.display_name}</td><td><Badge tone="accent">{mapping.source_transaction_type}</Badge></td>
        <td>{mapping.transaction_type.replaceAll("_", " ")}</td>
        <td>{["transfer", "credit_card_payment", "adjustment"].includes(mapping.transaction_type) ? "Excluded" : "Not auto-excluded"}</td>
        <td><button className="icon-button danger" onClick={() => deleteMapping("type", mapping.id)} aria-label={`Delete ${mapping.source_transaction_type} mapping`}><Trash2 size={15}/></button></td>
      </tr>) : <tr><td colSpan={5} className="muted">No provider transaction type mappings yet.</td></tr>}</tbody>
    </table></div></div>

    {modal && <div className="modal-backdrop"><div className="modal">
      <div className="modal-header"><h2>Add {modal}</h2><button className="icon-button" onClick={() => setModal(null)}><X/></button></div>
      {error && <div className="notice notice-error">{error}</div>}
      <form onSubmit={submit}>
        {modal === "provider category" && <div className="form-grid">
          <InstitutionField institutions={institutions}/>
          <div className="field"><label>Institution category</label><input className="input" name="source" required placeholder="Shopping"/></div>
          <div className="field"><label>App category</label><select className="select" name="category" value={parent} onChange={(event) => {
            const categoryId = event.target.value;
            const category = categories.find((candidate) => candidate.id === categoryId);
            setParent(categoryId);
            setProviderSubcategory(soleActiveSubcategoryId(category) || "");
          }} required>
            <option value="">Choose category</option>{categories.filter((category) => category.is_active).map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
          </select></div>
          <div className="field"><label>App subcategory</label><select className="select" name="subcategory" value={providerSubcategory} onChange={(event) => setProviderSubcategory(event.target.value)}>
            <option value="">No subcategory</option>{categories.find((category) => category.id === parent)?.subcategories.filter((subcategory) => subcategory.is_active).map((subcategory) => <option key={subcategory.id} value={subcategory.id}>{subcategory.name}</option>)}
          </select></div>
        </div>}
        {modal === "provider type" && <div className="form-grid">
          <InstitutionField institutions={institutions}/>
          <div className="field"><label>Provider transaction type</label><input className="input" name="source" required placeholder="Sale"/></div>
          <div className="field"><label>Ledgerly transaction type</label><select className="select" name="transaction_type" required>
            {transactionTypes.map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}
          </select></div>
        </div>}
        {(modal === "category" || modal === "subcategory") && <>
          <div className="field"><label>Name</label><input className="input" name="name" required/></div>
          <div className="field" style={{ marginTop: 14 }}><label>Description</label><textarea className="textarea" name="description"/></div>
        </>}
        <div className="form-actions"><button type="button" className="button" onClick={() => setModal(null)}>Cancel</button><button className="button button-primary">Save</button></div>
      </form>
    </div></div>}
  </>;
}

function InstitutionField({ institutions }: { institutions: Institution[] }) {
  return <div className="field"><label>Financial institution</label><select className="select" name="institution_id" required>
    <option value="">Choose institution</option>{institutions.filter((institution) => institution.is_active).map((institution) => <option key={institution.id} value={institution.id}>{institution.display_name}</option>)}
  </select></div>;
}
