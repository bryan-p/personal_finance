"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BarChart3, CircleDollarSign, CreditCard, FolderTree, LogOut, RefreshCw, ScrollText, Upload, WalletCards } from "lucide-react";
import { api } from "@/lib/api";

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
  useEffect(() => {
    api<{ display_name: string }>("/auth/me").then((user) => setName(user.display_name)).catch(() => router.replace("/login"));
  }, [router]);
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

