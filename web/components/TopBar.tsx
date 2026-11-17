import Link from "next/link";
import { apiGet } from "@/lib/api";
import type { Me } from "@/lib/types";
import { LogoutButton } from "./LogoutButton";

export async function TopBar() {
  const me = await apiGet<Me>("/me");
  const links = [{ href: "/reviews", label: "我的覆核" }];
  if (me.is_admin) {
    links.push({ href: "/campaigns", label: "覆核活動" }, { href: "/findings", label: "發現" }, { href: "/policy", label: "規則" }, { href: "/people", label: "查人" });
  }
  return (
    <header className="bg-cabinet text-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3">
        <Link href="/reviews" className="font-tag text-lg font-semibold tracking-[0.2em]">KEYWARD</Link>
        <nav className="flex min-w-0 flex-wrap gap-4 text-sm text-white/80">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-white">{l.label}</Link>
          ))}
        </nav>
        <div className="ml-auto flex min-w-0 items-center gap-3 text-sm">
          <span className="truncate">{me.name}<span className="ml-1.5 text-white/60">{me.title}</span></span>
          <LogoutButton />
        </div>
      </div>
    </header>
  );
}
