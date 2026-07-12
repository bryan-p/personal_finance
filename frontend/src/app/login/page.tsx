"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter(); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); const data = new FormData(event.currentTarget);
    try { await api("/auth/login", { method: "POST", body: JSON.stringify({ email: data.get("email"), password: data.get("password") }) }); router.replace("/dashboard"); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not log in"); setBusy(false); }
  }
  return <div className="auth-page"><section className="auth-art"><div className="brand"><span className="brand-mark">$</span><span>Ledgerly</span></div><div><h1>Your money,<br/>made legible.</h1><p>Turn scattered bank and card exports into one private, calm view of where your money goes.</p></div><small>Local-first · No telemetry · Your PostgreSQL</small></section><section className="auth-panel"><div className="auth-form"><h2>Welcome back</h2><p>Sign in to your private financial workspace.</p>{error && <div className="notice notice-error">{error}</div>}<form onSubmit={submit}><div className="field"><label>Email address</label><input className="input" name="email" type="email" required autoComplete="email" /></div><div className="field"><label>Password</label><input className="input" name="password" type="password" required autoComplete="current-password" /></div><button className="button button-primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button></form><div className="auth-switch">New to Ledgerly? <Link href="/register">Create an account</Link></div></div></section></div>;
}

