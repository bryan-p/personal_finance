"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BarChart3, CircleDollarSign, CreditCard, FolderTree, LogOut, RefreshCw, ScrollText, Upload, WalletCards } from "lucide-react";
import { api, ApiError } from "@/lib/api";

const links = [
  ["/dashboard", "Dashboard", BarChart3],
  ["/accounts", "Accounts", WalletCards],
  ["/imports", "Import CSV", Upload],
  ["/transactions", "Transactions", CircleDollarSign],
  ["/categories", "Categories", FolderTree],
  ["/rules", "Rules", ScrollText],
  ["/recurring", "Recurring", RefreshCw],
] as const;

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [name, setName] = useState("");
  const [authState, setAuthState] = useState<"checking" | "authenticated" | "redirecting" | "error">("checking");
  const [authError, setAuthError] = useState("");
  useEffect(() => {
    let active = true;
    api<{ display_name: string }>("/auth/me")
      .then((user) => {
        if (!active) return;
        setName(user.display_name);
        setAuthState("authenticated");
      })
      .catch((reason) => {
        if (!active) return;
        if (reason instanceof ApiError && reason.status === 401) {
          setAuthState("redirecting");
          router.replace("/login");
          return;
        }
        setAuthError(reason instanceof Error ? reason.message : "Could not verify your session");
        setAuthState("error");
      });
    return () => { active = false; };
  }, [router]);

  if (authState === "checking" || authState === "redirecting") {
    return <div className="auth-check" role="status">Checking your session…</div>;
  }
  if (authState === "error") {
    return <div className="auth-check"><div className="notice notice-error">{authError}</div><button className="button" onClick={() => window.location.reload()}>Try again</button></div>;
  }

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    router.replace("/login");
  }
  return <div className="app-shell">
    <aside className="sidebar">
      <Link href="/dashboard" className="brand"><span className="brand-mark"><CreditCard size={20} /></span><span>Ledgerly</span></Link>
      <nav>{links.map(([href, label, Icon]) => <Link key={href} href={href} className={pathname.startsWith(href) ? "active" : ""}><Icon size={18} /><span>{label}</span></Link>)}</nav>
      <div className="sidebar-user"><div className="avatar">{name.slice(0, 1).toUpperCase() || "U"}</div><div><strong>{name || "Local user"}</strong><small>Private workspace</small></div><button className="icon-button" onClick={logout} title="Log out"><LogOut size={17} /></button></div>
    </aside>
    <main className="main-content">{children}</main>
  </div>;
}
