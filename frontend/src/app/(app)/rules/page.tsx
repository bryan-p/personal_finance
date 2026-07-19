"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Badge, EmptyState, PageHeader } from "@/components/Page";
import { RuleForm } from "@/components/RuleForm";
import { api } from "@/lib/api";
import type { Category, Rule } from "@/lib/types";

type RuleModal = { mode: "create" } | { mode: "edit"; rule: Rule };

function display(value: string) {
  return value.replaceAll("_", " ");
}

export default function RulesPage() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [modal, setModal] = useState<RuleModal | null>(null);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [deletingRuleId, setDeletingRuleId] = useState<string | null>(null);

  async function load() {
    const [loadedRules, loadedCategories] = await Promise.all([
      api<Rule[]>("/rules"),
      api<Category[]>("/categories"),
    ]);
    setRules(loadedRules);
    setCategories(loadedCategories);
  }

  useEffect(() => {
    void load().catch((reason) => {
      setError(reason instanceof Error ? reason.message : "Could not load rules");
    });
  }, []);

  function openCreate() {
    setError("");
    setFeedback("");
    setModal({ mode: "create" });
  }

  function openEdit(rule: Rule) {
    setError("");
    setFeedback("");
    setModal({ mode: "edit", rule });
  }

  function savedRule(saved: Rule, mode: "create" | "edit") {
    setRules((current) => {
      const next = mode === "edit"
        ? current.map((rule) => rule.id === saved.id ? saved : rule)
        : [...current, saved];
      return next.sort((left, right) => left.priority - right.priority || left.created_at.localeCompare(right.created_at));
    });
    setModal(null);
    setFeedback(`Rule “${saved.name}” ${mode === "edit" ? "updated" : "created"}.`);
  }

  async function toggle(rule: Rule) {
    setError("");
    setFeedback("");
    try {
      const saved = await api<Rule>(`/rules/${rule.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !rule.is_active }),
      });
      setRules((current) => current.map((candidate) => candidate.id === saved.id ? saved : candidate));
      setFeedback(`Rule “${saved.name}” ${saved.is_active ? "enabled" : "disabled"}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update rule status");
    }
  }

  async function deleteRule(rule: Rule) {
    if (!window.confirm(`Permanently delete rule “${rule.name}”? It will no longer apply to future imports.`)) return;
    setDeletingRuleId(rule.id);
    setError("");
    setFeedback("");
    try {
      await api(`/rules/${rule.id}`, { method: "DELETE" });
      setRules((current) => current.filter((candidate) => candidate.id !== rule.id));
      setFeedback(`Rule “${rule.name}” deleted.`);
      try {
        await load();
      } catch (reason) {
        const detail = reason instanceof Error ? reason.message : "Could not refresh rules";
        setError(`Rule was deleted, but the list could not be refreshed: ${detail}`);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete rule");
    } finally {
      setDeletingRuleId(null);
    }
  }

  function configuredActions(rule: Rule) {
    const actions: string[] = [];
    const category = categories.find((candidate) => candidate.id === rule.category_id);
    const subcategory = category?.subcategories.find((candidate) => candidate.id === rule.subcategory_id);
    if (category) actions.push(subcategory ? `${category.name} / ${subcategory.name}` : category.name);
    if (rule.transaction_type) actions.push(`Type: ${display(rule.transaction_type)}`);
    if (rule.is_excluded_from_spending !== null) actions.push(rule.is_excluded_from_spending ? "Exclude from spending" : "Include in spending");
    if (rule.mark_as_recurring !== null) actions.push(rule.mark_as_recurring ? "Mark recurring" : "Mark not recurring");
    if (rule.merchant_name_override) actions.push(`Merchant: ${rule.merchant_name_override}`);
    if (rule.note) actions.push(`Add note: ${rule.note}`);
    return actions.length ? actions.join(" · ") : "No changes configured";
  }

  return <>
    <PageHeader
      eyebrow="Automation"
      title="Category rules"
      description="Rules run in priority order during normalization. Every applied change stays visible in import review."
      actions={<button className="button button-primary" onClick={openCreate}><Plus size={16}/>New rule</button>}
    />
    {error && <div className="notice notice-error">{error}</div>}
    {feedback && <div className="notice notice-good">{feedback}</div>}
    {!rules.length ? <div className="card">
      <EmptyState
        title="No automation yet"
        body="Create a rule for recurring descriptions, merchants, account profiles, amounts, or provider categories."
        action={<button className="button button-primary" onClick={openCreate}>Create rule</button>}
      />
    </div> : <div className="card table-card">
      <div className="table-scroll">
        <table className="data-table">
          <thead><tr><th>Priority</th><th>Rule</th><th>When</th><th>Actions</th><th>Status</th><th>Manage</th></tr></thead>
          <tbody>{rules.map((rule) => {
            const isDeleting = deletingRuleId === rule.id;
            return <tr key={rule.id}>
              <td>{rule.priority}</td>
              <td><strong>{rule.name}</strong></td>
              <td><Badge tone="accent">{display(rule.match_field)}</Badge> {display(rule.match_operator)} <strong>{rule.match_value}</strong></td>
              <td>{configuredActions(rule)}</td>
              <td><button className="button" onClick={() => toggle(rule)} disabled={isDeleting}><Badge tone={rule.is_active ? "good" : "neutral"}>{rule.is_active ? "enabled" : "disabled"}</Badge></button></td>
              <td><div className="page-actions">
                <button className="button" onClick={() => openEdit(rule)} disabled={isDeleting}>Edit</button>
                <button className="button button-danger" onClick={() => deleteRule(rule)} disabled={deletingRuleId !== null}>
                  <Trash2 size={15}/>{isDeleting ? "Deleting…" : "Delete"}
                </button>
              </div></td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    </div>}
    {modal && <RuleForm
      categories={categories}
      mode={modal.mode}
      rule={modal.mode === "edit" ? modal.rule : undefined}
      onClose={() => setModal(null)}
      onSuccess={(saved) => savedRule(saved, modal.mode)}
    />}
  </>;
}
