"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter(); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setBusy(true); setError(""); const data = new FormData(event.currentTarget); try { await api("/auth/register", { method: "POST", body: JSON.stringify({ display_name: data.get("name"), email: data.get("email"), password: data.get("password") }) }); router.replace("/dashboard"); } catch (err) { setError(err instanceof Error ? err.message : "Could not register"); setBusy(false); } }
  return <div className="auth-page"><section className="auth-art"><div className="brand"><span className="brand-mark">$</span><span>Ledgerly</span></div><div><h1>Start with<br/>a clear view.</h1><p>Your categories, transactions, and account data stay on this computer—organized and ready when you are.</p></div><small>Local-first · No telemetry · Your PostgreSQL</small></section><section className="auth-panel"><div className="auth-form"><h2>Create your workspace</h2><p>Starter categories are created automatically.</p>{error && <div className="notice notice-error">{error}</div>}<form onSubmit={submit}><div className="field"><label>Your name</label><input className="input" name="name" required autoComplete="name" /></div><div className="field"><label>Email address</label><input className="input" name="email" type="email" required autoComplete="email" /></div><div className="field"><label>Password</label><input className="input" name="password" type="password" required minLength={8} autoComplete="new-password" /></div><button className="button button-primary" disabled={busy}>{busy ? "Creating…" : "Create account"}</button></form><div className="auth-switch">Already have an account? <Link href="/login">Sign in</Link></div></div></section></div>;
}

